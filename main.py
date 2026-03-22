import random

import pygame

# Constants
WIDTH, HEIGHT = 800, 600
EDGE_MARGIN = 100
NUM_BOIDS = 50
MAX_SPEED = 4
MAX_FORCE = 0.1
PERCEPTION_RADIUS = 80
SEPARATION_RADIUS = 30
ALIGNMENT_WEIGHT = 0.09
COHESION_WEIGHT = 0.005
SEPARATION_WEIGHT = 0.08
TURN = 1
enlightenment_chance = 5000


class Boid:
    def __init__(self, x, y, vx, vy):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.gx = 0
        self.gy = 0

    def separation(self, boids):
        for i in boids:
            dif_x = self.x - i.x
            dif_y = self.y - i.y
            distance = (dif_x**2 + dif_y**2) ** 0.5
            if distance < SEPARATION_RADIUS and distance > 0:
                self.vx += dif_x / distance * SEPARATION_WEIGHT
                self.vy += dif_y / distance * SEPARATION_WEIGHT

    def alignment(self, boids):
        for i in boids:
            if (self.x - i.x) ** 2 + (self.y - i.y) ** 2 < PERCEPTION_RADIUS**2:
                self.vx += i.vx * ALIGNMENT_WEIGHT / NUM_BOIDS
                self.vy += i.vy * ALIGNMENT_WEIGHT / NUM_BOIDS

    def cohesion(self, boids):
        x_sum = 0
        y_sum = 0
        count = 0
        for i in boids:
            if (self.x - i.x) ** 2 + (self.y - i.y) ** 2 < (PERCEPTION_RADIUS) ** 2:
                dist = ((self.x - i.x) ** 2 + (self.y - i.y) ** 2) ** 0.5
                if dist < PERCEPTION_RADIUS:
                    x_sum += i.x
                    y_sum += i.y
                    count += 1
        x_avg = x_sum / count if count > 0 else 0
        y_avg = y_sum / count if count > 0 else 0
        self.vx += (x_avg - self.x) * COHESION_WEIGHT
        self.vy += (y_avg - self.y) * COHESION_WEIGHT

    def limit_speed(self):
        speed = (self.vx**2 + self.vy**2) ** 0.5
        if speed > MAX_SPEED:
            self.vx = (self.vx / speed) * MAX_SPEED
            self.vy = (self.vy / speed) * MAX_SPEED

    def edges(self):
        if self.x < EDGE_MARGIN:
            self.vx += TURN
        elif self.x > WIDTH - EDGE_MARGIN:
            self.vx -= TURN
        if self.y < EDGE_MARGIN:
            self.vy += TURN
        elif self.y > HEIGHT - EDGE_MARGIN:
            self.vy -= TURN

    def enlightenment(self):
        if random.randint(0, enlightenment_chance) == random.randint(
            0, enlightenment_chance
        ):
            self.gx += random.uniform(-10, 10)
            self.gy += random.uniform(-10, 10)
        if self.gx != 0:
            self.vx += self.gx * 0.05
            self.gx += -self.gx * 0.05
        if self.gy != 0:
            self.vy += self.gy * 0.05
            self.gy += -self.gy * 0.05

    def update(self, boids):
        self.edges()
        self.separation(boids)
        self.alignment(boids)
        self.cohesion(boids)
        self.enlightenment()
        self.limit_speed()
        self.x += self.vx
        self.y += self.vy


pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

boids = [
    Boid(
        random.randint(0, WIDTH),
        random.randint(0, HEIGHT),
        random.uniform(-2, 2),
        random.uniform(-2, 2),
    )
    for _ in range(NUM_BOIDS)
]

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    screen.fill((0, 0, 0))

    for boid in boids:
        boid.update(boids)
        pygame.draw.circle(screen, (255, 255, 255), (int(boid.x), int(boid.y)), 3)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
