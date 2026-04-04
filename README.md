# Boids in Your Terminal

Watch a chaotic ecosystem unfold right in your terminal. This is a boids simulation—those classical flocking birds that somehow manage to be both predictable and gloriously messy all at once.

## What's Happening Here?

You've got a bunch of little critters (boids) bouncing around following three simple rules:

- **Separation**: don't crash into your friends (basic manners)
- **Alignment**: swim/fly in the same direction as your neighbors (peer pressure works)
- **Cohesion**: stick together-ish (lonely is not fun)

But that would be boring, so we added some chaos:

### Predators

Angry crosses hunting our poor boids. They're rather slow, but insistent. Currently implemented with a simple follow-nearest greedy algorithm. Watch the boids scatter!

### Allures

Shimmering points that our little boids find irresistible. Boids will often head for these even with predators nearby. Bad life choices make for good entertainment :D

### Random Enlightenment

Sometimes boids just _get it_ and wander off. Celebrate their brief moment of philosophical awakening before they go back to being confused little dots. Originally implemented to reduce clustering and overly predictable patterns.

## How to Run It

```bash
python main.py
```

Default constants are decently sensible – in my opinion :) – but feel free to pass cli flags to tweak behaviour. Some behaviours require flags.

```bash
python main.py -h # Check flags
python main.py --boid-density 1750 # Custom density (pixel-acres per boid)
python main.py --allure-chance 35 # 1/35 chance per frame; required for allures to spawn
```

Control it as you watch:

- **Q**: quit

Your terminal is the world. Watch it all unfold in beautiful Braille pixel art.
