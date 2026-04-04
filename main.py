import argparse
import fcntl
import math
import os
import random
import select
import shutil
import sys
import termios
import time
import tty
from collections import defaultdict

from drawille import Canvas

# Configurable constants
PREDATOR_SPAWN_DENSITY = 10000
BOID_SPAWN_DENSITY = 2250
MAX_SPEED = 5
ALIGNMENT_WEIGHT = 0.035
COHESION_WEIGHT = 0.003
SEPARATION_WEIGHT = 0.10
TURN = 0.75
ENLIGHTENMENT_CHANCE = 5000
MIN_SPEED = 0.7
# Perception and separation radii are now calculated dynamically based on terminal size, but these factors can be adjusted for different behaviors.
# Actual radius is equal to terminal_width (assuming width > height) / factor, clamped to a minimum of 1.
PERCEPTION_RADIUS_FACTOR = 6
SEPARATION_RADIUS_FACTOR = 8
ANTICENTRE_FACTOR = 0.0001
ANTICLUSTER_RADIUS_FACTOR = 11
ANTICLUSTER_FACTOR = 0.001
ALLURE_DETECTION_RADIUS_FACTOR = 3
ALLURING_WEIGHT = 15
ALLURE_LIFETIME = 20
PREDATOR_AVOIDANCE_WEIGHT = 5
PREDATOR_SEPARATION = 0.1
NOISE_STRENGTH = 0.01


TARGET_FRAME_TIME = 0.11


class Allure:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.frame_animation_base = [
            (2, 2),
            (2, 1),
            (2, 0),
            (2, -1),
            (2, -2),
            (-2, 2),
            (-2, 1),
            (-2, 0),
            (-2, -1),
            (-2, -2),
            (1, 2),
            (0, 2),
            (-1, 2),
            (1, -2),
            (0, -2),
            (-1, -2),
        ]
        self.frame_animation_dynamic = [
            [(0, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)],
            [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)],
        ]
        self.frame_count = 0

    def animate(self):
        base = self.frame_animation_base

        dynamic_frame = self.frame_count % len(self.frame_animation_dynamic)
        dynamic = self.frame_animation_dynamic[dynamic_frame]

        self.frame_count += 1
        return base, dynamic


class SpatialHash:
    def __init__(self, cell_size):
        self.cell_size = cell_size
        self.cells = defaultdict(list)

    def _hash(self, x, y):
        return int(x // self.cell_size), int(y // self.cell_size)

    def insert(self, boid):
        cell = self._hash(boid.x, boid.y)
        self.cells[cell].append(boid)

    def query(self, x, y):
        cell_x, cell_y = self._hash(x, y)
        nearby_boids = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cell = (cell_x + dx, cell_y + dy)
                nearby_boids.extend(self.cells.get(cell, []))
        return nearby_boids

    def pred_query(self, x, y):
        cell_x, cell_y = self._hash(x, y)
        nearby_predators = []
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                cell = (cell_x + dx, cell_y + dy)
                nearby_predators.extend(self.cells.get(cell, []))
        return nearby_predators

    def clear(self):
        for lst in self.cells.values():
            lst.clear()


class Predator:
    def __init__(self, x, y, vx, vy):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy

    def update(
        self,
        boids,
        world_width,
        world_height,
        accel_factor,
        centering_force,
        min_speed,
        max_speed,
        predators,
        predator_separation,
        turn,
        noise,
    ):
        # Move towards nearest boid
        if boids:
            nearest_boid = min(
                boids, key=lambda b: (self.x - b.x) ** 2 + (self.y - b.y) ** 2
            )
            self.vx += (nearest_boid.x - self.x) * accel_factor
            self.vy += (nearest_boid.y - self.y) * accel_factor

        # Move away from other predators
        for p in predators:
            if p is self:
                continue
            dx = self.x - p.x
            dy = self.y - p.y
            dist_sq = dx * dx + dy * dy
            if dist_sq == 0:
                continue
            inv = 1.0 / dist_sq
            inv = min(inv, 100.0)
            self.vx += dx * inv * predator_separation
            self.vy += dy * inv * predator_separation

        # Move towards centre
        self.vx += (world_width / 2 - self.x) * centering_force
        self.vy += (world_height / 2 - self.y) * centering_force

        # Move away from edges
        edge_margin = min(world_width, world_height) // 10
        if self.x < edge_margin * 3:
            self.vx += turn
        elif self.x > world_width - edge_margin * 3:
            self.vx -= turn
        if self.y < edge_margin * 3:
            self.vy += turn
        elif self.y > world_height - edge_margin * 3:
            self.vy -= turn

        # Noise
        self.vx += random.uniform(-noise, noise)
        self.vy += random.uniform(-noise, noise)

        speed_sq = self.vx * self.vx + self.vy * self.vy

        # Enforce min and max speed
        if speed_sq == 0:
            self.vx = 0.3 * min_speed * random.choice([-1, 1])
            self.vy = 0.3 * min_speed * random.choice([-1, 1])
            self.x += self.vx
            self.y += self.vy
            self.x = max(0, min(world_width - 1, self.x))
            self.y = max(0, min(world_height - 1, self.y))
            return
        if speed_sq < min_speed * min_speed:
            scale = min_speed / math.sqrt(speed_sq)
            self.vx *= scale
            self.vy *= scale
        elif speed_sq > max_speed * max_speed:
            scale = max_speed / math.sqrt(speed_sq)
            self.vx *= scale
            self.vy *= scale

        self.x += self.vx
        self.y += self.vy
        self.x = max(0, min(world_width - 1, self.x))
        self.y = max(0, min(world_height - 1, self.y))


class Boid:
    def __init__(self, x, y, vx, vy):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.gx = 0
        self.gy = 0
        self.angle = 0

    def update_flocking(
        self,
        boids,
        perception_radius,
        separation_radius,
        alignment_weight,
        cohesion_weight,
        separation_weight,
    ):
        sep_sq = separation_radius * separation_radius
        per_sq = perception_radius * perception_radius

        sep_vx, sep_vy = 0.0, 0.0
        align_vx, align_vy = 0.0, 0.0
        coh_x, coh_y = 0.0, 0.0
        align_count, coh_count = 0, 0

        for other in boids:
            dx = self.x - other.x
            dy = self.y - other.y
            dist_sq = dx * dx + dy * dy

            if dist_sq == 0:
                continue  # Skip self, minor but probably not needed (apart from removing division by zero?)

            # Separation
            if dist_sq < sep_sq:
                inv = 1.0 / dist_sq
                inv = min(inv, 100.0)
                sep_vx += dx * inv
                sep_vy += dy * inv

            # Alignment and cohesion
            if dist_sq < per_sq:
                align_vx += other.vx
                align_vy += other.vy
                coh_x += other.x
                coh_y += other.y
                align_count += 1
                coh_count += 1

        self.vx += sep_vx * separation_weight
        self.vy += sep_vy * separation_weight

        if align_count:
            self.vx += ((align_vx / align_count) - self.vx) * alignment_weight
            self.vy += ((align_vy / align_count) - self.vy) * alignment_weight
            # Both align and cohesion use the same count, so no need to check them separately; that's rather redundant :)
            self.vx += ((coh_x / coh_count) - self.x) * cohesion_weight
            self.vy += ((coh_y / coh_count) - self.y) * cohesion_weight

    def clamp_speed(self, min_speed, max_speed):
        speed_sq = self.vx * self.vx + self.vy * self.vy
        if speed_sq == 0:
            self.vx = 0.7 * min_speed * random.choice([-1, 1])
            self.vy = 0.7 * min_speed * random.choice([-1, 1])
            return
        speed = math.sqrt(speed_sq)
        if speed > max_speed:
            scale = max_speed / speed
        elif speed < min_speed:
            scale = min_speed / speed
        else:
            return
        self.vx *= scale
        self.vy *= scale

    def edges(self, world_width, world_height, edge_margin, turn):
        if self.x < edge_margin:
            self.vx += turn
        elif self.x > world_width - edge_margin:
            self.vx -= turn
        if self.y < edge_margin:
            self.vy += turn
        elif self.y > world_height - edge_margin:
            self.vy -= turn

    def enlightenment(self, enlightenment_chance):
        if random.randint(0, enlightenment_chance) == 0:
            self.gx += random.uniform(-10, 10)
            self.gy += random.uniform(-10, 10)
        if self.gx != 0:
            self.vx += self.gx * 0.05
            self.gx *= 0.85
        if self.gy != 0:
            self.vy += self.gy * 0.05
            self.gy *= 0.85

    def anticentre(self, total_width, total_height, anticentre_factor):
        target_x, target_y = total_width / 2, total_height / 2
        self.vx += (self.x - target_x) * anticentre_factor
        self.vy += (self.y - target_y) * anticentre_factor

    def anticluster(self, boids, anticluster_radius, anticluster_factor):
        x_mean = 0.0
        y_mean = 0.0
        count = 0
        radius_sq = anticluster_radius * anticluster_radius
        for b in boids:
            dx = self.x - b.x
            dy = self.y - b.y
            dist_sq = dx * dx + dy * dy
            if 0 < dist_sq < radius_sq:
                x_mean += b.x
                y_mean += b.y
                count += 1
        if count > 0:
            x_mean /= count
            y_mean /= count
            self.vx += (self.x - x_mean) * anticluster_factor
            self.vy += (self.y - y_mean) * anticluster_factor

    def update(
        self,
        boids,
        world_width,
        world_height,
        edge_margin,
        perception_radius,
        separation_radius,
        anticluster_radius,
        min_speed,
        max_speed,
        predator_avoidance_weight,
        anticluster_factor,
        anticentre_factor,
        alignment_weight,
        cohesion_weight,
        separation_weight,
        turn,
        enlightenment_chance,
        noise,
        allure_detection_radius_factor,
        allure_weight,
        predators=None,
        allure=None,
    ):
        self.edges(world_width, world_height, edge_margin, turn)

        # Flee from nearby predators
        if predators:
            pred_vx, pred_vy = 0.0, 0.0
            for p in predators:
                dx = self.x - p.x
                dy = self.y - p.y
                dist_sq = dx * dx + dy * dy
                if dist_sq == 0:
                    continue
                inv = 1.0 / dist_sq
                inv = min(inv, 100.0)
                pred_vx += dx * inv
                pred_vy += dy * inv
            # Apply predator avoidance influence
            self.vx += pred_vx * predator_avoidance_weight
            self.vy += pred_vy * predator_avoidance_weight

        if allure:
            for a in allure:
                dx = a.x - self.x
                dy = a.y - self.y
                dist_sq = dx * dx + dy * dy
                if (
                    dist_sq
                    > (min(world_width, world_height) / allure_detection_radius_factor)
                    ** 2
                ):
                    continue
                if dist_sq == 0:
                    continue
                inv = 1.0 / dist_sq
                inv = min(inv, 100.0)
                self.vx += dx * inv * allure_weight
                self.vy += dy * inv * allure_weight

        self.update_flocking(
            boids,
            perception_radius,
            separation_radius,
            alignment_weight,
            cohesion_weight,
            separation_weight,
        )
        self.anticentre(world_width, world_height, anticentre_factor)
        self.anticluster(boids, anticluster_radius, anticluster_factor)
        self.enlightenment(enlightenment_chance)
        self.vx += random.uniform(-noise, noise)
        self.vy += random.uniform(-noise, noise)
        self.clamp_speed(min_speed, max_speed)
        self.x += self.vx
        self.y += self.vy
        self.angle = int(round(math.atan2(-self.vy, self.vx) / (math.pi / 4))) % 8
        self.x = max(0, min(world_width - 1, self.x))
        self.y = max(0, min(world_height - 1, self.y))


def terminal_geometry():
    terminal_size = shutil.get_terminal_size(fallback=(80, 24))
    term_cols = max(1, terminal_size.columns)
    term_rows = max(1, terminal_size.lines)
    world_width = term_cols * 2
    world_height = term_rows * 4
    return term_cols, term_rows, world_width, world_height


def simulation_radii(
    world_width,
    world_height,
    perception_factor,
    separation_factor,
    anticluster_factor,
):
    # Use the smaller world dimension so radii scale consistently with terminal size.
    min_dim = min(world_width, world_height)
    edge_margin = max(1, min_dim // 10)
    perception_radius = max(1, min_dim // perception_factor)
    separation_radius = max(1, min_dim // separation_factor)
    anticluster_radius = max(1, min_dim // anticluster_factor)
    return edge_margin, perception_radius, separation_radius, anticluster_radius


# Relative pixel offsets for each of the 8 directions (0-7)
# 0: East, 1: NE, 2: North, 3: NW, 4: West, 5: SW, 6: South, 7: SE
ARROW_PIXELS = {
    0: [(0, 0), (-1, 0), (-2, 0), (-1, -1), (-1, 1), (-3, 0)],  # →
    1: [(0, 0), (-1, 1), (-2, 2), (0, 1), (-1, 0)],  # ↗
    2: [(0, 0), (0, 1), (0, 2), (-1, 1), (1, 1), (0, 3)],  # ↑
    3: [(0, 0), (1, 1), (2, 2), (0, 1), (1, 0)],  # ↖
    4: [(0, 0), (1, 0), (2, 0), (1, -1), (1, 1), (3, 0)],  # ←
    5: [(0, 0), (1, -1), (2, -2), (0, -1), (1, 0)],  # ↙
    6: [(0, 0), (0, -1), (0, -2), (-1, -1), (1, -1), (0, -3)],  # ↓
    7: [(0, 0), (-1, -1), (-2, -2), (0, -1), (-1, 0)],  # ↘
}


def render(
    boids,
    term_cols,
    term_rows,
    world_width,
    world_height,
    boid_count=None,
    predators=None,
    allure=None,
):
    canvas = Canvas()

    for boid in boids:
        # Get the pixel offsets for the current direction
        offsets = ARROW_PIXELS.get(boid.angle, [(0, 0)])

        for dx, dy in offsets:
            # Draw the boid's "body" pixels
            px = boid.x + dx
            py = boid.y + dy

            if 0 <= px < world_width and 0 <= py < world_height:
                canvas.set(px, py)

    # Draw predators as a small cross so they're visible on the canvas
    if predators:
        pred_offsets = [
            (0, 0),
            (1, 0),
            (-1, 0),
            (0, 1),
            (0, -1),
            (0, 2),
            (0, -2),
            (2, 0),
            (-2, 0),
        ]
        for pred in predators:
            for dx, dy in pred_offsets:
                px = pred.x + dx
                py = pred.y + dy
                if 0 <= px < world_width and 0 <= py < world_height:
                    canvas.set(px, py)

    if allure:
        for a in allure:
            base, dynamic = a.animate()
            for dx, dy in base + dynamic:
                px = a.x + dx
                py = a.y + dy
                if 0 <= px < world_width and 0 <= py < world_height:
                    canvas.set(px, py)

    body = canvas.frame(
        min_x=0,
        min_y=0,
        max_x=world_width,
        max_y=world_height,
    )

    lines = body.splitlines()
    if len(lines) < term_rows:
        lines.extend([""] * (term_rows - len(lines)))
    lines = [line.ljust(term_cols)[:term_cols] for line in lines[:term_rows]]

    # Overlay simple metrics at the bottom-left
    metrics = ""
    if boid_count is not None:
        metrics += f"BOIDS:{boid_count}"
    if predators:
        metrics += f" PRED:{len(predators)}"

    if metrics:
        last_idx = term_rows - 1
        line = lines[last_idx]
        m = metrics[:term_cols]
        lines[last_idx] = m + line[len(m) :]

    return "\n".join(lines)


def args():
    parser = argparse.ArgumentParser(description="Terminal boids simulation!")

    # Population density
    parser.add_argument(
        "--boid-density",
        type=int,
        default=BOID_SPAWN_DENSITY,
        help="Pixel-acres per boid (lower is denser)",
    )
    parser.add_argument(
        "--predator-density",
        type=int,
        default=PREDATOR_SPAWN_DENSITY,
        help="Pixel-acres per predator (lower is denser)",
    )
    parser.add_argument(
        "--no-predators",
        action="store_true",
        help="Disable predators entirely",
    )

    # Speed parameters
    parser.add_argument(
        "--max-speed",
        type=float,
        default=MAX_SPEED,
        help="Maximum speed for boids",
    )
    parser.add_argument(
        "--min-speed",
        type=float,
        default=MIN_SPEED,
        help="Minimum speed for boids",
    )

    # Flocking behavior weights
    parser.add_argument(
        "--alignment-weight",
        type=float,
        default=ALIGNMENT_WEIGHT,
        help="Alignment force weight",
    )
    parser.add_argument(
        "--cohesion-weight",
        type=float,
        default=COHESION_WEIGHT,
        help="Cohesion force weight",
    )
    parser.add_argument(
        "--separation-weight",
        type=float,
        default=SEPARATION_WEIGHT,
        help="Separation force weight",
    )

    # Perception and separation radii factors
    parser.add_argument(
        "--perception-factor",
        type=int,
        default=PERCEPTION_RADIUS_FACTOR,
        help="Perception radius factor (world_dim / factor)",
    )
    parser.add_argument(
        "--separation-factor",
        type=int,
        default=SEPARATION_RADIUS_FACTOR,
        help="Separation radius factor (world_dim / factor)",
    )

    # Anticluster and anticentre
    parser.add_argument(
        "--anticluster-factor",
        type=float,
        default=ANTICLUSTER_FACTOR,
        help="Anticluster force weight",
    )
    parser.add_argument(
        "--anticluster-radius-factor",
        type=int,
        default=ANTICLUSTER_RADIUS_FACTOR,
        help="Anticluster radius factor (world_dim / factor)",
    )
    parser.add_argument(
        "--anticentre-factor",
        type=float,
        default=ANTICENTRE_FACTOR,
        help="Anticentre force weight",
    )

    # Enlightenment
    parser.add_argument(
        "--enlightenment-chance",
        type=int,
        default=ENLIGHTENMENT_CHANCE,
        help="Enlightenment chance (1 in N per frame)",
    )

    # Predator behavior
    parser.add_argument(
        "--predator-avoidance-weight",
        type=float,
        default=PREDATOR_AVOIDANCE_WEIGHT,
        help="Predator avoidance force weight",
    )
    parser.add_argument(
        "--predator-separation",
        type=float,
        default=PREDATOR_SEPARATION,
        help="Predator mutual separation weight",
    )

    # Edge behavior
    parser.add_argument(
        "--turn",
        type=float,
        default=TURN,
        help="Edge turning force magnitude",
    )

    parser.add_argument(
        "--noise-strength",
        type=float,
        default=NOISE_STRENGTH,
        help="Random noise strength added to velocity each frame",
    )

    # Frame rate
    parser.add_argument(
        "--frame-time",
        type=float,
        default=TARGET_FRAME_TIME,
        help="Target frame time in seconds",
    )

    parser.add_argument(
        "--allure-chance",
        type=int,
        default=-1,
        help="Chance for an allure to spawn (1 in N per frame)",
    )

    parser.add_argument(
        "--allure-lifetime",
        type=int,
        default=ALLURE_LIFETIME,
        help="Lifetime of an allure in frames",
    )

    parser.add_argument(
        "--allure-detection-radius-factor",
        type=int,
        default=ALLURE_DETECTION_RADIUS_FACTOR,
        help="Detection radius factor for allure (world_dim / factor)",
    )

    parser.add_argument(
        "--alluring-weight",
        type=float,
        default=ALLURING_WEIGHT,
        help="Weight of allure attraction force",
    )

    return parser.parse_args()


def validate_config(config):
    """Validate configuration parameters to prevent runtime errors."""
    errors = []

    if config.boid_density <= 0:
        errors.append("--boid-density must be positive")
    if config.predator_density <= 0:
        errors.append("--predator-density must be positive")
    if config.max_speed <= 0:
        errors.append("--max-speed must be positive")
    if config.min_speed < 0:
        errors.append("--min-speed must be non-negative")
    if config.min_speed >= config.max_speed:
        errors.append("--min-speed must be less than --max-speed")
    if config.perception_factor <= 0:
        errors.append("--perception-factor must be positive")
    if config.separation_factor <= 0:
        errors.append("--separation-factor must be positive")
    if config.anticluster_radius_factor <= 0:
        errors.append("--anticluster-radius-factor must be positive")
    if config.enlightenment_chance <= 0:
        errors.append("--enlightenment-chance must be positive")
    if config.frame_time <= 0:
        errors.append("--frame-time must be positive")

    if errors:
        print("Configuration errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)


def main():
    # Parse and validate config first, before any terminal modifications
    config = args()
    validate_config(config)

    # Ensure we're running in a terminal
    if not sys.stdin.isatty():
        print(
            "Error: This program must be run in a terminal (stdin is not a TTY)",
            file=sys.stderr,
        )
        sys.exit(1)

    # Save original terminal/file descriptor settings
    origin_flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
    origin_stdout_flags = fcntl.fcntl(sys.stdout, fcntl.F_GETFL)
    origin_term = termios.tcgetattr(sys.stdin)

    try:
        # Configure stdin as non-blocking
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, origin_flags | os.O_NONBLOCK)

        # Ensure stdout is blocking
        fcntl.fcntl(sys.stdout, fcntl.F_SETFL, origin_stdout_flags & ~os.O_NONBLOCK)

        # Use cbreak mode instead of raw to allow Ctrl+C to work
        tty.setcbreak(sys.stdin)

        term_cols, term_rows, world_width, world_height = terminal_geometry()

        # Initialize boids, and predators only if enabled
        num_boids = (world_width * world_height) // config.boid_density
        boids = [
            Boid(
                random.uniform(0, world_width - 1),
                random.uniform(0, world_height - 1),
                random.uniform(-config.max_speed, config.max_speed),
                random.uniform(-config.max_speed, config.max_speed),
            )
            for _ in range(num_boids)
        ]

        if config.no_predators:
            predators = []
        else:
            predators = [
                Predator(
                    random.uniform(0, world_width - 1),
                    random.uniform(0, world_height - 1),
                    random.uniform(-config.max_speed, config.max_speed),
                    random.uniform(-config.max_speed, config.max_speed),
                )
                for _ in range((world_width * world_height) // config.predator_density)
            ]

        allure = []

        sys.stdout.write("\033[?25l")
        sys.stdout.write("\033[H")

        edge_margin, perception_radius, separation_radius, anticluster_radius = (
            simulation_radii(
                world_width,
                world_height,
                config.perception_factor,
                config.separation_factor,
                config.anticluster_radius_factor,
            )
        )
        spatial_hash = SpatialHash(cell_size=perception_radius)
        predator_hash = SpatialHash(cell_size=perception_radius)
        last_geometry = (term_cols, term_rows)

        try:
            while True:
                term_cols, term_rows, world_width, world_height = terminal_geometry()

                if (
                    config.allure_chance > 0
                    and random.randint(0, config.allure_chance) == 0
                ):
                    allure.append(
                        Allure(
                            random.uniform(
                                edge_margin * 2, world_width - edge_margin * 2
                            ),
                            random.uniform(
                                edge_margin * 2, world_height - edge_margin * 2
                            ),
                        )
                    )

                # Updating spatial hash if terminal resizes
                if (term_cols, term_rows) != last_geometry:
                    last_geometry = (term_cols, term_rows)
                    (
                        edge_margin,
                        perception_radius,
                        separation_radius,
                        anticluster_radius,
                    ) = simulation_radii(
                        world_width,
                        world_height,
                        config.perception_factor,
                        config.separation_factor,
                        config.anticluster_radius_factor,
                    )
                    spatial_hash = SpatialHash(cell_size=perception_radius)
                    predator_hash = SpatialHash(cell_size=perception_radius)

                # Boids :D
                spatial_hash.clear()
                for boid in boids:
                    spatial_hash.insert(boid)
                predator_hash.clear()
                for predator in predators:
                    predator_hash.insert(predator)

                for boid in boids:
                    neighbours = spatial_hash.query(boid.x, boid.y)
                    nearby_predators = predator_hash.query(boid.x, boid.y)
                    boid.update(
                        neighbours,
                        world_width,
                        world_height,
                        edge_margin,
                        perception_radius,
                        separation_radius,
                        anticluster_radius,
                        config.min_speed,
                        config.max_speed,
                        config.predator_avoidance_weight,
                        config.anticluster_factor,
                        config.anticentre_factor,
                        config.alignment_weight,
                        config.cohesion_weight,
                        config.separation_weight,
                        config.turn,
                        config.enlightenment_chance,
                        config.noise_strength,
                        config.allure_detection_radius_factor,
                        config.alluring_weight,
                        predators=nearby_predators,
                        allure=allure,
                    )
                for predator in predators:
                    nearby_boids = spatial_hash.pred_query(predator.x, predator.y)
                    nearby_predators = predator_hash.pred_query(predator.x, predator.y)
                    predator.update(
                        nearby_boids,
                        world_width,
                        world_height,
                        accel_factor=0.05,
                        centering_force=0.0005,
                        min_speed=config.min_speed,
                        max_speed=config.max_speed * 0.3,
                        predators=nearby_predators,
                        predator_separation=config.predator_separation,
                        turn=config.turn,
                        noise=config.noise_strength,
                    )

                allure = [a for a in allure if a.frame_count <= config.allure_lifetime]

                if select.select([sys.stdin], [], [], 0)[0]:
                    c = sys.stdin.read(1)
                    if c and c.lower() == "q":
                        break
                    if c == "\x03":  # Ctrl+C
                        break

                sys.stdout.write(
                    "\033[H"
                    + render(
                        boids,
                        term_cols,
                        term_rows,
                        world_width,
                        world_height,
                        boid_count=len(boids),
                        predators=predators,
                        allure=allure,
                    )
                )
                sys.stdout.flush()
                time.sleep(config.frame_time)

        except KeyboardInterrupt:
            pass
        finally:
            # Restore terminal to original state
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, origin_term)
            fcntl.fcntl(sys.stdin, fcntl.F_SETFL, origin_flags)
            fcntl.fcntl(sys.stdout, fcntl.F_SETFL, origin_stdout_flags)
            sys.stdout.write("\033[H")
            sys.stdout.write("\033[?25h\n")
    except KeyboardInterrupt:
        pass
    finally:
        # Ensure terminal is always restored, even if setup fails
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, origin_term)
            fcntl.fcntl(sys.stdin, fcntl.F_SETFL, origin_flags)
            fcntl.fcntl(sys.stdout, fcntl.F_SETFL, origin_stdout_flags)
            sys.stdout.write("\033[?25h\n")
        except Exception as e:
            sys.stderr.write(
                f"\033[?25h\nWarning: failed to restore terminal state: {e}\n"
            )


if __name__ == "__main__":
    main()
