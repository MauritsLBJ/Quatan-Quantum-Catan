# src/ui.py
# Game UI: buttons, panels, input handling and drawing coordination

import pygame
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

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_click(event.pos)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                # cancel placement/trade
                self.state.sel = None
                self.state.placing = False
                self.trade_mode = False
                self.trade_give = None

    def _handle_click(self, pos):
        state = self.state
        mx,my = pos
        # check buttons first
        if rect_contains(self.state.reset_rect, pos):
            state.reset_game()
            return
        if rect_contains(self.state.dice_rect, pos) and "rolling" in self.state.allowed_actions:
            state.roll_and_distribute()
            return
        if rect_contains(self.state.end_turn_rect, pos) and "endTurn" in self.state.allowed_actions:
            state.end_turn()
            return
        if rect_contains(self.state.trade_rect, pos) and "trading" in self.state.allowed_actions:
            self.state.trading = not self.state.trading
            return
        
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
                    self.state.sel = None
                    self.placing = False
                else:
                    if self.state.round < 0:
                        if k == "village" or k == "road":
                            self.state.sel = k
                            self.state.placing = self.state.sel
                        else:
                            self.state.push_message("Can only place villages and roads during initial placement.")
                    elif self.state.round >= 0 and self.state.player_can_afford(self.state.current_player, k):
                        self.state.sel = k
                        self.state.placing = self.state.sel
                return

        # placement logic
        if self.state.placing and self.state.sel:
            if self.state.sel in ("village","city"):
                nearest = self.state.find_nearest_intersection(pos)
                if nearest is not None:
                    if self.state.sel == "village":
                        if self.state.can_place_settlement(nearest):
                            if self.state.round < 0:
                                if self.state.villages_placed <= 2+self.state.round:
                                    self.state.place_settlement(nearest, self.state.current_player, "village")
                                    self.state.sel = None
                                    self.state.placing = False
                                    self.state.villages_placed += 1
                                    if self.state.round == -1:
                                        # give resources for 2nd settlement
                                        self.state.give_initial_settlement_resources(nearest, self.state.current_player)
                                else:
                                    self.state.push_message("Cannot place more villages this round.")
                            elif self.state.player_buy(self.state.current_player, "village"):
                                self.state.place_settlement(nearest, self.state.current_player, "village")
                                self.state.sel = None
                                self.state.placing = False
                                self.state.villages_placed += 1
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
                        if self.state.round < 0:
                            if self.state.roads_placed <= 2+self.state.round:
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
        elif self.state.moving_robber:
            tile_idx = self.state.find_nearest_tile(pos)
            if tile_idx is not None and tile_idx != self.state.robber_idx:
                self.state.move_robber_to(tile_idx)
                self.state.moving_robber = False
        elif self.state.entangling:
            tile_idx = self.state.find_nearest_tile(pos)
            resource_list = [t.get("resource") for t in self.state.entangling_pair]
            if tile_idx is not None and tile_idx != self.state.robber_idx:
                tile = self.state.tiles[tile_idx]
                if tile in self.state.entangling_pair:
                    self.state.push_message("Already selected this tile. Select a different quantum tile.")
                elif tile.get("quantum", False):
                    self.state.push_message("Selected tile is quantum. Select a classical tile.")
                elif tile.get("resource") == "desert":
                    self.state.push_message("Cannot entangle desert tile. Select a different classical tile.")
                
                elif tile.get("resource") in resource_list:
                    self.state.push_message("Cannot entangle two tiles of the same resource type. Select a different classical tile.")
                else:
                    self.state.entangling_pair.append(tile)
                    if len(self.state.entangling_pair) == 2:
                        self.state.entangle_pair_of_normal_tiles(self.state.entangling_pair, self.state.unused_ent_group_number)
                        self.state.entangling_pair = []
                        self.state.entangling = False 
                    
        else: # inspection mode
            tile_idx = self.state.find_nearest_tile(pos)
            tile = self.state.tiles[tile_idx] if tile_idx is not None else None
            self.state.push_message(f"Inspected tile:")
            if tile and tile.get("quantum"):
                entangled_with_coord = None
                for entTile in self.state.tiles:
                    if entTile.get("ent_group") == tile.get("ent_group") and entTile != tile:
                        entangled_with_coord = entTile.get("coord")
                        break
                self.state.push_message(f"- Possible resources: {tile.get('superposed')[0]} and {tile.get('superposed')[1]}")
                self.state.push_message(f"- entangled with coord: {entangled_with_coord}")
            else:
                self.state.push_message(f"- Resource: {tile.get('resource') if tile else 'N/A'}")

    def draw(self):
        s = self.screen
        s.fill(BG_COLOR)
        self.state.draw()  # the game state handles low-level drawing

