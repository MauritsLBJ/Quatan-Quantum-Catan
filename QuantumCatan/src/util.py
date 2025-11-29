# src/util.py
import math
from .constants import SQRT3

def hex_to_pixel(q, r, size=50, origin=(0,0)):
    ox, oy = origin
    x = size * SQRT3 * (q + r/2)
    y = size * 1.5 * r
    return (ox + x, oy + y)

def polygon_corners(center, size=50):
    cx, cy = center
    pts = []
    start_angle = math.radians(30)
    for i in range(6):
        ang = start_angle + math.radians(60 * i)
        pts.append((cx + size * math.cos(ang), cy + size * math.sin(ang)))  
    return pts

def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])
