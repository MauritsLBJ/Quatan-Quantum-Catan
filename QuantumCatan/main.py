# main.py
# Run this to start Quantum Catan
import time
import pygame
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
    screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)

    num_players =  2 #ask_player_count()
    state = GameState(num_players=num_players, screen=screen)
    ui = GameUI(state, screen)
    
    lis = []
    n = 0
    her_we_go = True
    shi = True
    while len(lis) < 2:
        if state.tiles[n].get("ent_group") != None:
            if shi:
                id = state.tiles[n].get("ent_group")
                tile = state.tiles[n]
                lis.append(tile)
                shi = False
            else:
                if state.tiles[n].get("ent_group") == id:
                    tile = state.tiles[n]
                    lis.append(tile)
        n += 1
    print(lis)
    clock = pygame.time.Clock()
    running = True
    while running:
        dt = clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            ui.handle_event(event)

        state.update(dt)
        ui.draw()
        pygame.display.flip()
        
        if her_we_go:
            time.sleep(5)
            her_we_go = False
            state.unentagle_pair_of_quantum_tiles(lis)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
