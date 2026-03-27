import math
import random
import shutil
import sys
import time

from drawille import Canvas

# Configurable constants
NUM_BOIDS = 50
MAX_SPEED = 4
EDGE_MARGIN = 100
PERCEPTION_RADIUS = 120
SEPARATION_RADIUS = 50
ALIGNMENT_WEIGHT = 0.09
COHESION_WEIGHT = 0.003
SEPARATION_WEIGHT = 0.08
TURN = 1
ENLIGHTENMENT_CHANCE = 5000

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
        for i in boids:
            dif_x = self.x - i.x
            dif_y = self.y - i.y
            distance = (dif_x**2 + dif_y**2) ** 0.5
            if distance < separation_radius and distance > 0:
                self.vx += dif_x / distance * SEPARATION_WEIGHT
                self.vy += dif_y / distance * SEPARATION_WEIGHT

    def alignment(self, boids, perception_radius):
        for i in boids:
            if (self.x - i.x) ** 2 + (self.y - i.y) ** 2 < perception_radius**2:
                self.vx += i.vx * ALIGNMENT_WEIGHT / NUM_BOIDS
                self.vy += i.vy * ALIGNMENT_WEIGHT / NUM_BOIDS

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
            self.gx *= 0.95
        if self.gy != 0:
            self.vy += self.gy * 0.05
            self.gy *= 0.95

    def update(
        self,
        boids,
        world_width,
        world_height,
        edge_margin,
        perception_radius,
        separation_radius,
    ):
        self.edges(world_width, world_height, edge_margin)
        self.separation(boids, separation_radius)
        self.alignment(boids, perception_radius)
        self.cohesion(boids, perception_radius)
        self.enlightenment()
        self.limit_speed()
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


def simulation_radii(world_width, world_height):
    edge_margin = max(1, min(EDGE_MARGIN, world_width // 4, world_height // 4))
    perception_radius = max(
        1, min(PERCEPTION_RADIUS, world_width // 2, world_height // 2)
    )
    separation_radius = max(
        1, min(SEPARATION_RADIUS, world_width // 5, world_height // 5)
    )
    return edge_margin, perception_radius, separation_radius


def init(world_width, world_height):
    sys.stdout.write("\033[?25l")
    sys.stdout.write("\033[H")
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


def render(boids, term_cols, term_rows, world_width, world_height):
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

    return "\n".join(lines)


def main():
    term_cols, term_rows, world_width, world_height = terminal_geometry()
    boids = init(world_width, world_height)

    try:
        while True:
            # Adaptive constants (clamped to current terminal size)
            term_cols, term_rows, world_width, world_height = terminal_geometry()
            edge_margin, perception_radius, separation_radius = simulation_radii(
                world_width, world_height
            )
            for boid in boids:
                boid.update(
                    boids,
                    world_width,
                    world_height,
                    edge_margin,
                    perception_radius,
                    separation_radius,
                )
            sys.stdout.write(
                "\033[H"
                + render(boids, term_cols, term_rows, world_width, world_height)
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
