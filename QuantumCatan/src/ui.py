# src/ui.py
# Game UI: buttons, panels, input handling and drawing coordination

import pygame, copy
from .constants import BG_COLOR, PANEL_BG, LINE_COLOR, TEXT_COLOR, HIGHLIGHT, INVALID_COLOR, BUTTON_COLOR, WHITE, BLACK, PLAYER_COLORS
from .util import dist
from .board import compute_centers_and_polys, compute_sea_polys, HEX_COORDS  # used only for structure in imports
from .util import polygon_corners
from .game_state import GameState

def rect_contains(rect, pos):
    return rect.collidepoint(pos)

class GameUI:
    def __init__(self, state: GameState, screen):
        self.state = state
        self.screen = screen

    def handle_event(self, g_event):
        if g_event.type == pygame.MOUSEBUTTONDOWN and g_event.button == 1:
            self._handle_click(g_event.pos)
        if g_event.type == pygame.KEYDOWN:
            if g_event.key == pygame.K_ESCAPE:
                # cancel placement
                self.state.sel = None
                self.state.placing = False
                self.state.entangling_pair = []
            else:
                self.handle_dev_clicks(g_event)
            
            
    def handle_dev_clicks(self, g_event):
        if self.state.devMode == True:
            if g_event.unicode.isdigit():
                self.state.roll_and_distribute(g_event.unicode) 
            if g_event.key == pygame.K_u:
                self.state.unentangle_pair_of_quantum_tiles(self.state.tiles[self.state.find_nearest_tile(pygame.mouse.get_pos())])
            if g_event.key == pygame.K_e:
                self.state.entangling = not self.state.entangling
            
            
        
            
    

    

    def _handle_click(self, pos):
        state = self.state
        mx,my = pos
        # check buttons first
        if self.state.runningGame == False and self.state.playerWon == False:
            for i in range(len(self.state.num_player_buttons)):
                if rect_contains(self.state.num_player_buttons[i][1], pos):
                    self.button_clicked()
                    self.state.num_players = (i+2)  # 2-4 players
                    return
            for i in range(len(self.state.entanglement_buttons)):
                if rect_contains(self.state.entanglement_buttons[i][1], pos):
                    self.button_clicked()
                    self.state.num_entangled_pairs = (i+1)  # 1-3 entanglements
                    return
            if rect_contains(self.state.start_button, pos):
                self.button_clicked()
                self.state.start_game()
                return
        elif self.state.playerWon:
            # game over screen click
            if rect_contains(self.state.restart_button, pos):
                self.button_clicked()
                self.state.playerWon = False
                return
            
        else:
            if rect_contains(self.state.reset_rect, pos):
                self.button_clicked()
                state.reset_game()
                
                return
            if rect_contains(self.state.dice_rect, pos) and ("rolling" in self.state.allowed_actions or self.state.devMode == True):
                self.button_clicked()
                state.roll_and_distribute(None)
                
                return
            if rect_contains(self.state.end_turn_rect, pos) and ("endTurn" in self.state.allowed_actions or self.state.devMode == True):
                self.button_clicked()
                state.end_turn()
                
                return
            if rect_contains(self.state.trade_rect, pos) and ("trading" in self.state.allowed_actions or self.state.devMode == True):
                yesOrNo = True if self.state.trading == False else False
                self.button_clicked()
                self.state.trading = yesOrNo
                print(self.state.trading)
                return
            if rect_contains(self.state.devMode_rect, pos) and self.state.devMode == False:
                self.button_clicked()
                self.state.devMode = True
                self.state.round = 5
                self.state.push_message("Developer mode activated.")
                for player in self.state.players:
                    player.resources = {"lumber":100,"brick":100,"wool":100,"grain":100,"ore":100}
            if rect_contains(self.state.inspect_rect, pos):
                yesOrNo = True if self.state.inspecting == False else False
                self.button_clicked()
                self.state.inspecting = yesOrNo
            elif self.state.inspecting: # inspection mode
                tile_idx = self.state.find_nearest_tile(pos)
                tile = self.state.tiles[tile_idx] if tile_idx is not None else None
                self.state.push_message(f"Inspected tile:")
                if tile and tile_idx is not None and tile.get("quantum"):
                    entangled_with_coord = None
                    for entTile in self.state.tiles:
                        if entTile.get("ent_group") == tile.get("ent_group") and entTile != tile:
                            entangled_with_coord = entTile.get("coord")
                            break
                    self.state.push_message(f"- Possible resources: {tile.get('superposed')[0]} and {tile.get('superposed')[1]}")
                    self.state.push_message(f"- entangled with coord: {entangled_with_coord}")
                else:
                    self.state.push_message(f"- Resource: {tile.get('resource') if tile else 'N/A'}")
            
            # if trading mode: select give then receive via panels
            if self.state.trading:
                # check inventory give buttons
                for res, rect in enumerate(self.state.trading_partners_rects):
                    if rect_contains(rect, pos):
                        if self.state.possible_trading_partners[res] == "Bank/port":
                            self.state.trading_partner = "bank/port"
                        else:
                            self.state.trading_partner = self.state.possible_trading_partners[res]
                        break
                    return
            
            if self.state.possible_victims:
                for res, rect in enumerate(self.state.possible_victims_rects):
                    if rect_contains(rect, pos):
                        self.state.victim = self.state.possible_victims[res]
                        self.state.steal_from_victim(self.state.current_player, self.state.victim)
                        self.state.possible_victims = []
                        return

            # shop clicks
            for k, rect in self.state.shop_rects:
                if rect_contains(rect, pos):
                    # toggle selection
                    if self.state.sel == k:
                        self.button_clicked()
                        self.state.sel = None
                        self.state.placing = False
                    else:
                        self.button_clicked()
                        if self.state.round < 2:
                            if k == "settlement":
                                if self.state.settlements_placed == 0:
                                    self.state.sel = k
                                    self.state.placing = self.state.sel
                                else:
                                    self.state.push_message("You already placed a settlement this initial placement turn")
                            elif k == "road":
                                if self.state.settlements_placed == 1:
                                    if self.state.roads_placed == 0:
                                        self.state.sel = k
                                        self.state.placing = self.state.sel
                                    else:
                                        self.state.push_message("You already placed a road this initial placement turn")
                                else:
                                    self.state.push_message("First, place a settlement before placing a road")
                            else:
                                self.state.push_message("Can only place settlements and roads during initial placement.")
                        elif self.state.player_can_afford(self.state.current_player, k):
                            if "building" in self.state.allowed_actions or self.state.devMode == True:
                                self.state.sel = k
                                self.state.placing = self.state.sel
                            else:
                                self.state.push_message("Cannot build right now.")
                        else:
                            self.state.push_message("Can't afford")
                    return

            # placement logic
            if self.state.placing and self.state.sel:
                if self.state.sel in ("settlement","city"):
                    nearest = self.state.find_nearest_intersection(pos)
                    if nearest is not None:
                        if self.state.sel == "settlement":
                            if self.state.can_place_settlement(nearest):
                                if self.state.round < 2:
                                    if self.state.settlements_placed == 0:
                                        self.state.place_settlement(nearest, self.state.current_player, "settlement")
                                        self.state.sel = None
                                        self.state.placing = False
                                        self.state.settlements_placed += 1
                                        if self.state.round == 1:
                                            # give resources for 2nd settlement
                                            self.state.give_initial_settlement_resources(nearest, self.state.current_player)
                                            print("Gave initial resources for settlement at", nearest)
                                    else:
                                        self.state.push_message("Cannot place more settlements this round.")
                                elif self.state.player_buy(self.state.current_player, "settlement"):
                                    self.state.place_settlement(nearest, self.state.current_player, "settlement")
                                    self.state.sel = None
                                    self.state.placing = False
                                    self.state.settlements_placed += 1
                        else:
                            # city
                            if self.state.can_upgrade_to_city(self.state.current_player, nearest):
                                if self.state.player_buy(self.state.current_player, "city"):
                                    self.state.upgrade_to_city(nearest, self.state.current_player)
                                    self.state.sel = None
                                    self.state.placing = False
                elif self.state.sel == "road":
                    nearest = self.state.find_nearest_road(pos)
                    if nearest is not None:
                        if self.state.can_place_road_slot(nearest):
                            if self.state.round < 2:
                                if self.state.roads_placed == 0:
                                    self.state.place_road(nearest, self.state.current_player)
                                    self.state.sel = None
                                    self.state.placing = False
                                    self.state.roads_placed += 1
                                else:
                                    self.state.push_message("Cannot place more roads this round.")
                            elif self.state.player_buy(self.state.current_player, "road"):
                                self.state.place_road(nearest, self.state.current_player)
                                self.state.sel = None
                                self.state.placing = False
                                self.state.roads_placed += 1
            elif self.state.moving_robber and self.state.inspecting == False:
                tile_idx = self.state.find_nearest_tile(pos)
                if tile_idx is not None and tile_idx != self.state.robber_idx:
                    self.state.move_robber_to(tile_idx)
                    self.state.moving_robber = False
            elif self.state.entangling and self.state.inspecting == False:
                tile_idx = self.state.find_nearest_tile(pos)
                resource_list = [t.get("resource") for idx, t in self.state.entangling_pair]
                if tile_idx is not None and tile_idx != self.state.robber_idx:
                    tile = self.state.tiles[tile_idx]
                    if tile in self.state.entangling_pair:
                        self.state.push_message("Already selected this tile. Select a different quantum tile.")
                    elif tile.get("quantum", False):
                        self.state.push_message("Selected tile is quantum. Select a classical tile.")
                    elif tile.get("resource") == "desert":
                        self.state.push_message("Cannot entangle desert tile. Select a different tile.")
                    
                    elif tile.get("resource") in resource_list:
                        self.state.push_message("Cannot entangle two tiles of the same resource type. Select a different tile.")
                    else:
                        self.state.entangling_pair.append((tile_idx, tile))
                        if len(self.state.entangling_pair) == 2:
                            self.state.unused_ent_group_numbers.sort()
                            print("entangling tiles:", self.state.entangling_pair)
                            self.state.entangle_pair_of_normal_tiles(self.state.entangling_pair, self.state.unused_ent_group_numbers.pop(0))
                            self.state.entangling_pair = []
                            self.state.entangling = False 

    def button_clicked(self):
        self.state.inspecting = False #if button != self.state.inspect_rect else self.state.inspecting
        self.state.trading = False #if button != self.state.trade_rect else self.state.trading
        self.state.placing = False #if button not in self.state.shop_rects else self.state.placing
        self.state.sel = None #if button not in self.state.shop_rects else self.state.sel
        
                    
        

    def draw(self):
        s = self.screen
        s.fill(BG_COLOR)
        if self.state.runningGame:
            self.state.draw()  # the game state handles low-level drawing
        elif self.state.playerWon == False:
            self.state.draw_start_screen()
        else:
            self.state.draw_game_over_screen()

