import math
import random
import shutil
import sys
import time

from drawille import Canvas

# Configurable constants
BOID_SPAWN_DENSITY = 1000
MAX_SPEED = 5
ALIGNMENT_WEIGHT = 0.035
COHESION_WEIGHT = 0.003
SEPARATION_WEIGHT = 0.20
TURN = 0.5
ENLIGHTENMENT_CHANCE = 50000
MIN_SPEED = 0.7
# Perception and separation radii are now calculated dynamically based on terminal size, but these factors can be adjusted for different behaviors.
# Actual radius is equal to terminal_width (assuming width>height) / factor, clamped to a minimum of 1.
PERCEPTION_RADIUS_FACTOR = 6
SEPARATION_RADIUS_FACTOR = 8
ANTICENTRE_FACTOR = 0.0001


TARGET_FRAME_TIME = 0.1


class Boid:
    def __init__(self, x, y, vx, vy):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.gx = 0
        self.gy = 0
        self.angle = 0

    def separation(self, boids, separation_radius):
        sep_sq = separation_radius * separation_radius
        for i in boids:
            dx = self.x - i.x
            dy = self.y - i.y
            dist_sq = dx * dx + dy * dy
            if 0 < dist_sq < sep_sq:
                inv = 1.0 / dist_sq
                inv = min(inv, 100.0)
                self.vx += dx * inv * SEPARATION_WEIGHT
                self.vy += dy * inv * SEPARATION_WEIGHT

    def alignment(self, boids, perception_radius):
        vx_sum = 0.0
        vy_sum = 0.0
        count = 0
        pr2 = perception_radius * perception_radius
        for i in boids:
            dx = self.x - i.x
            dy = self.y - i.y
            if dx * dx + dy * dy < pr2:
                vx_sum += i.vx
                vy_sum += i.vy
                count += 1
        if count > 0:
            avg_vx = vx_sum / count
            avg_vy = vy_sum / count
            self.vx += (avg_vx - self.vx) * ALIGNMENT_WEIGHT
            self.vy += (avg_vy - self.vy) * ALIGNMENT_WEIGHT

    def cohesion(self, boids, perception_radius):
        x_sum, y_sum, count = 0, 0, 0
        for i in boids:
            if (self.x - i.x) ** 2 + (self.y - i.y) ** 2 < perception_radius**2:
                x_sum += i.x
                y_sum += i.y
                count += 1
        if count > 0:
            self.vx += (x_sum / count - self.x) * COHESION_WEIGHT
            self.vy += (y_sum / count - self.y) * COHESION_WEIGHT

    def limit_speed(self):
        speed = (self.vx**2 + self.vy**2) ** 0.5
        if speed > MAX_SPEED:
            self.vx = (self.vx / speed) * MAX_SPEED
            self.vy = (self.vy / speed) * MAX_SPEED

    def min_speed(self, min_speed):
        speed = self.vx**2 + self.vy**2
        if speed < min_speed**2 and speed > 0:
            self.vx = self.vx * 1.5
            self.vy = self.vy * 1.5

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

    def anticentre(self, total_height, total_width, anticentre_factor):
        target_x, target_y = total_width / 2, total_height / 2
        self.vx += (self.x - target_x) * anticentre_factor
        self.vy += (self.y - target_y) * anticentre_factor

    def update(
        self,
        boids,
        world_width,
        world_height,
        edge_margin,
        perception_radius,
        separation_radius,
        min_speed=0.5,
        anticluster_factor=0.001,
        anticentre_factor=0.0001,
    ):
        self.edges(world_width, world_height, edge_margin)
        self.separation(boids, separation_radius)
        self.alignment(boids, perception_radius)
        self.cohesion(boids, perception_radius)
        self.anticentre(world_height, world_width, anticentre_factor)
        self.enlightenment()
        self.limit_speed()
        self.min_speed(min_speed)
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
):
    edge_margin = max(1, world_width // 10, world_height // 10)
    perception_radius = max(1, world_width // perception_factor, perception_factor // 6)
    separation_radius = max(1, separation_factor // 11, separation_factor // 11)
    return edge_margin, perception_radius, separation_radius


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

    return boids


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


def render(boids, term_cols, term_rows, world_width, world_height, boid_count=None):
    canvas = Canvas()

    for boid in boids:
        # Get the pixel offsets for the current direction
        offsets = ARROW_PIXELS.get(boid.angle, [(0, 0)])

        for dx, dy in offsets:
            # Draw the boid's "body" pixels
            # We use boid.x + dx to draw the shape relative to the boid
            px = boid.x + dx
            py = boid.y + dy

            # Stay within world bounds to avoid Canvas errors
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
        if metrics:
            metrics += " "
        metrics += f"BOIDS:{boid_count}"

    if metrics:
        last_idx = term_rows - 1
        line = lines[last_idx]
        m = metrics[:term_cols]
        lines[last_idx] = m + line[len(m) :]

    return "\n".join(lines)


def main():
    term_cols, term_rows, world_width, world_height = terminal_geometry()
    boids = init(world_width, world_height)
    last_time = time.time()
    fps = 0.0

    try:
        while True:
            now = time.time()
            elapsed = now - last_time
            last_time = now
            if elapsed > 0:
                instant_fps = 1.0 / elapsed
                fps = (fps * 0.9) + (instant_fps * 0.1) if fps else instant_fps

            # Adaptive constants (clamped to current terminal size)
            term_cols, term_rows, world_width, world_height = terminal_geometry()
            edge_margin, perception_radius, separation_radius = simulation_radii(
                world_width,
                world_height,
                PERCEPTION_RADIUS_FACTOR,
                SEPARATION_RADIUS_FACTOR,
            )
            for boid in boids:
                boid.update(
                    boids,
                    world_width,
                    world_height,
                    edge_margin,
                    perception_radius,
                    separation_radius,
                    MIN_SPEED,
                    ANTICENTRE_FACTOR,
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
