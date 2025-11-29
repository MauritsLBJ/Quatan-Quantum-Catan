# src/constants.py
import pygame
WIN_W = 1100
WIN_H = 750

# Colors (solid color scheme)
BG_COLOR = (235, 222, 200)
PANEL_BG = (240, 230, 210)
LINE_COLOR = (60, 60, 60)
TEXT_COLOR = (20, 20, 20)
HIGHLIGHT = (100, 220, 120)
INVALID_COLOR = (230, 80, 80)
BUTTON_COLOR = (170, 80, 80)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

PLAYER_COLORS = [
    (200, 60, 60),   # red
    (60, 140, 200),  # blue
    (80, 160, 60),   # green
    (180, 120, 40)   # brown
]


HEX_RADIUS = 2
SEA_RING = HEX_RADIUS + 1

SQRT3 = 3 ** 0.5

def getFont(size=18):
    try:
        return pygame.font.Font("QuantumCatan/fonts/ScienceGothic-Regular.ttf", size)
    except:
        return pygame.font.SysFont("Arial", size)
