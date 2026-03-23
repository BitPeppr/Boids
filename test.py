import time

from termgraphics import TermGraphics

g = TermGraphics()

g.clear()

x = 1
y = 1
while True:
    x += 1
    y += 1
    x %= 200
    y %= 400
    g.clear()
    g.poly(((x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)))
    g.draw()
    time.sleep(0.1)
