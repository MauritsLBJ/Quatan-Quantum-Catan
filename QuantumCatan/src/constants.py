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

ENT_NUMBER_COLOURS = [
    (255, 0, 255), #rgb(255, 0, 255)
    (0, 255, 255), #rgb(0, 255, 255)
    (255, 103, 0), #rgb(255, 103, 0)
    (163, 229, 9), #rgb(163, 229, 9)
    (185, 226, 232), #rgb(185, 226, 232)
    (89, 69, 57),   #rgb(89, 69, 57)
    (21, 11, 40),  #rgb(21, 11, 40)
    (191, 191, 191), #rgb(191, 191, 191)
    (19, 25, 17),   #rgb(19, 25, 17)
    (253, 53, 180), #rgb(253, 53, 180)
    
]

DEV_CARD_COLORS = {
    "knight": (200, 60, 60), # rgb(200, 60, 60)
    "point": (60, 140, 200), # rgb(60, 140, 200)
    "interference": (80, 160, 60), # rgb(80, 160, 60)
    "Year of Plenty": (180, 120, 40), # rgb(180, 120, 40)
    "Monopoly": (255, 215, 0), # rgb(255, 215, 0)
    "roadBuilding": (139, 69, 19) # rgb(139, 69, 19)
}

PREVIEW_COLOR = {"good":BLACK, "bad":(139, 0, 0) #rgb(139, 0, 0)
}

HEX_RADIUS = 2
SEA_RING = HEX_RADIUS + 1

SQRT3 = 3 ** 0.5

def getFont(size=18):
    try:
        return pygame.font.Font("../fonts/ScienceGothic-Regular.ttf", size)
    except:
        return pygame.font.SysFont("Arial", size)
