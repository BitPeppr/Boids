import math
import random
import shutil
import sys
import time
from collections import defaultdict

from drawille import Canvas

# Configurable constants
PREDATOR_SPAWN_DENSITY = 10000
BOID_SPAWN_DENSITY = 1700
MAX_SPEED = 5
ALIGNMENT_WEIGHT = 0.035
COHESION_WEIGHT = 0.003
SEPARATION_WEIGHT = 0.05
TURN = 0.5
ENLIGHTENMENT_CHANCE = 5000
MIN_SPEED = 0.7
# Perception and separation radii are now calculated dynamically based on terminal size, but these factors can be adjusted for different behaviors.
# Actual radius is equal to terminal_width (assuming width > height) / factor, clamped to a minimum of 1.
PERCEPTION_RADIUS_FACTOR = 6
SEPARATION_RADIUS_FACTOR = 8
ANTICENTRE_FACTOR = 0.0001
ANTICLUSTER_RADIUS_FACTOR = 11
ANTICLUSTER_FACTOR = 0.001
PREDATOR_AVOIDANCE_WEIGHT = 5


TARGET_FRAME_TIME = 0.11


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
    ):
        # Move towards nearest boid
        nearest_boid = min(
            boids, key=lambda b: (self.x - b.x) ** 2 + (self.y - b.y) ** 2
        )
        self.vx += (nearest_boid.x - self.x) * accel_factor
        self.vy += (nearest_boid.y - self.y) * accel_factor

        # Move towards centre
        self.vx += (world_width / 2 - self.x) * centering_force
        self.vy += (world_height / 2 - self.y) * centering_force

        # Move away from edges
        edge_margin = min(world_width, world_height) // 10
        if self.x < edge_margin * 2:
            self.vx += TURN
        elif self.x > world_width - edge_margin * 2:
            self.vx -= TURN
        if self.y < edge_margin * 2:
            self.vy += TURN
        elif self.y > world_height - edge_margin * 2:
            self.vy -= TURN

        speed_sq = self.vx * self.vx + self.vy * self.vy

        # Enforce min and max speed
        if speed_sq == 0:
            self.vx = 0.3 * min_speed * random.choice([-1, 1])
            self.vy = 0.3 * min_speed * random.choice([-1, 1])
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


class Boid:
    def __init__(self, x, y, vx, vy):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.gx = 0
        self.gy = 0
        self.angle = 0

    def update_flocking(self, boids, perception_radius, separation_radius):
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

        self.vx += sep_vx * SEPARATION_WEIGHT
        self.vy += sep_vy * SEPARATION_WEIGHT

        if align_count:
            self.vx += ((align_vx / align_count) - self.vx) * ALIGNMENT_WEIGHT
            self.vy += ((align_vy / align_count) - self.vy) * ALIGNMENT_WEIGHT
            # Both align and cohesion use the same count, so no need to check them separately; that's rather redundant :)
            self.vx += ((coh_x / coh_count) - self.x) * COHESION_WEIGHT
            self.vy += ((coh_y / coh_count) - self.y) * COHESION_WEIGHT

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

    def edges(self, world_width, world_height, edge_margin):
        if self.x < edge_margin:
            self.vx += TURN
        elif self.x > world_width - edge_margin:
            self.vx -= TURN
        if self.y < edge_margin:
            self.vy += TURN
        elif self.y > world_height - edge_margin:
            self.vy -= TURN

    def enlightenment(self):
        if random.randint(0, ENLIGHTENMENT_CHANCE) == random.randint(
            0, ENLIGHTENMENT_CHANCE
        ):
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
        predator_avoidance_weight,
        anticluster_factor=0.001,
        anticentre_factor=0.0001,
        predators=None,
    ):
        self.edges(world_width, world_height, edge_margin)

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

        self.update_flocking(boids, perception_radius, separation_radius)
        self.anticentre(world_width, world_height, anticentre_factor)
        self.anticluster(boids, anticluster_radius, anticluster_factor)
        self.enlightenment()
        self.clamp_speed(min_speed, MAX_SPEED)
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
    perception_factor=PERCEPTION_RADIUS_FACTOR,
    separation_factor=SEPARATION_RADIUS_FACTOR,
    anticluster_factor=ANTICLUSTER_RADIUS_FACTOR,
):
    # Use the smaller world dimension so radii scale consistently with terminal size.
    min_dim = min(world_width, world_height)
    edge_margin = max(1, min_dim // 10)
    perception_radius = max(1, min_dim // perception_factor)
    separation_radius = max(1, min_dim // separation_factor)
    anticluster_radius = max(1, min_dim // anticluster_factor)
    return edge_margin, perception_radius, separation_radius, anticluster_radius


def init(world_width, world_height):
    sys.stdout.write("\033[?25l")
    sys.stdout.write("\033[H")
    NUM_BOIDS = (world_width * world_height) // BOID_SPAWN_DENSITY
    boids = [
        Boid(
            random.uniform(0, world_width - 1),
            random.uniform(0, world_height - 1),
            random.uniform(-MAX_SPEED, MAX_SPEED),
            random.uniform(-MAX_SPEED, MAX_SPEED),
        )
        for _ in range(NUM_BOIDS)
    ]
    predators = [
        Predator(
            random.uniform(0, world_width - 1),
            random.uniform(0, world_height - 1),
            random.uniform(-MAX_SPEED, MAX_SPEED),
            random.uniform(-MAX_SPEED, MAX_SPEED),
        )
        for _ in range((world_width * world_height) // PREDATOR_SPAWN_DENSITY)
    ]

    return boids, predators


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
        pred_offsets = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
        for pred in predators:
            for dx, dy in pred_offsets:
                px = pred.x + dx
                py = pred.y + dy
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


def main():
    term_cols, term_rows, world_width, world_height = terminal_geometry()
    boids, predators = init(world_width, world_height)
    edge_margin, perception_radius, separation_radius, anticluster_radius = (
        simulation_radii(
            world_width,
            world_height,
            PERCEPTION_RADIUS_FACTOR,
            SEPARATION_RADIUS_FACTOR,
            ANTICLUSTER_RADIUS_FACTOR,
        )
    )
    spatial_hash = SpatialHash(cell_size=perception_radius)
    predator_hash = SpatialHash(cell_size=perception_radius)
    last_geometry = (term_cols, term_rows)

    try:
        while True:
            term_cols, term_rows, world_width, world_height = terminal_geometry()

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
                    PERCEPTION_RADIUS_FACTOR,
                    SEPARATION_RADIUS_FACTOR,
                    ANTICLUSTER_RADIUS_FACTOR,
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
                    MIN_SPEED,
                    PREDATOR_AVOIDANCE_WEIGHT,
                    ANTICLUSTER_FACTOR,
                    ANTICENTRE_FACTOR,
                    predators=nearby_predators,
                )
            for predator in predators:
                nearby_boids = spatial_hash.pred_query(predator.x, predator.y)
                if nearby_boids:
                    predator.update(
                        nearby_boids,
                        world_width,
                        world_height,
                        accel_factor=0.05,
                        centering_force=0.0005,
                        min_speed=MIN_SPEED,
                        max_speed=MAX_SPEED * 0.3,
                    )
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
                )
            )
            sys.stdout.flush()
            time.sleep(TARGET_FRAME_TIME)

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[H")
        sys.stdout.write("\033[?25h\n")


if __name__ == "__main__":
    main()
