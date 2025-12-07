# main.py
# Run this to start Quantum Catan
import time
import pygame
from pygame.locals import *
import sys
from src.game_state import GameState
from src.ui import GameUI
from src.constants import WIN_W, WIN_H

"""
def ask_player_count():
     simple terminal prompt before launching pygame
    while True:
        try:
            val = input("Number of players (2-4) [default 4]: ").strip()
            if val == "":
                return 4
            n = int(val)
            if 2 <= n <= 4:
                return n
        except Exception:
            pass
        print("Please enter 2, 3 or 4.")
"""

def main():
    pygame.init()
    pygame.font.init()
    pygame.display.set_caption("Quantum Catan")
    screen = pygame.display.set_mode((WIN_W, WIN_H), HWSURFACE|DOUBLEBUF|RESIZABLE)

    num_players =  2 #ask_player_count()
    state = GameState(num_players=num_players, screen=screen)
    ui = GameUI(state, screen)

    clock = pygame.time.Clock()
    running = True
    while running:
        dt = clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            ui.handle_event(event)
            if event.type == VIDEORESIZE:
                width, height = event.size
                if width < 1100:
                    width = 1100
                if height < 700:
                    height = 700
                screen = pygame.display.set_mode((width,height), HWSURFACE|DOUBLEBUF|RESIZABLE)
                ui.screen = screen
                ui.state.screen = screen
    
        state.update(dt)
        ui.draw()
        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
