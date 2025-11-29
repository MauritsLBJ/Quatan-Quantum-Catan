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
        self.sel = None
        self.placing = False
        self.trade_mode = False
        self.trade_give = None

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_click(event.pos)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                # cancel placement/trade
                self.sel = None
                self.placing = False
                self.trade_mode = False
                self.trade_give = None

    def _handle_click(self, pos):
        state = self.state
        mx,my = pos
        # check buttons first
        if rect_contains(self.state.reset_rect, pos):
            state.reset_game()
            return
        if rect_contains(self.state.dice_rect, pos):
            state.roll_and_distribute()
            return
        if rect_contains(self.state.end_turn_rect, pos):
            state.end_turn()
            return
        if rect_contains(self.state.trade_rect, pos):
            self.trade_mode = not self.trade_mode
            self.trade_give = None
            return
        # if trading mode: select give then receive via panels
        if self.trade_mode:
            # check inventory give buttons
            clicked = False
            for res, rect in self.state.trade_give_rects:
                if rect_contains(rect, pos):
                    self.trade_give = res
                    clicked = True
                    break
            if clicked:
                return
            if self.trade_give:
                for res, rect in self.state.trade_recv_rects:
                    if rect_contains(rect, pos):
                        ok, ratio = self.state.perform_trade(self.state.current_player, self.trade_give, res)
                        self.trade_mode = False
                        self.trade_give = None
                        return
            return

        # shop clicks
        for k, rect in self.state.shop_rects:
            if rect_contains(rect, pos):
                # toggle selection
                if self.sel == k:
                    self.sel = None
                    self.placing = False
                else:
                    if self.state.player_can_afford(self.state.current_player, k):
                        self.sel = k
                        self.placing = True
                return

        # placement logic
        if self.placing and self.sel:
            if self.sel in ("village","city"):
                nearest = self.state.find_nearest_intersection(pos)
                if nearest is not None:
                    if self.sel == "village":
                        if self.state.can_place_settlement(nearest):
                            if self.state.player_buy(self.state.current_player, "village"):
                                self.state.place_settlement(nearest, self.state.current_player, "village")
                                self.sel = None
                                self.placing = False
                    else:
                        # city
                        if self.state.can_upgrade_to_city(self.state.current_player, nearest):
                            if self.state.player_buy(self.state.current_player, "city"):
                                self.state.upgrade_to_city(nearest, self.state.current_player)
                                self.sel = None
                                self.placing = False
            elif self.sel == "road":
                nearest = self.state.find_nearest_road(pos)
                if nearest is not None:
                    if self.state.can_place_road_slot(nearest):
                        if self.state.player_buy(self.state.current_player, "road"):
                            self.state.place_road(nearest, self.state.current_player)
                            self.sel = None
                            self.placing = False
        if self.state.moving_robber:
            tile_idx = self.state.find_nearest_tile(pos)
            if tile_idx is not None and tile_idx != self.state.robber_idx:
                self.state.move_robber_to(tile_idx)
                self.state.moving_robber = False
        if self.state.entangling:
            tile_idx = self.state.find_nearest_tile(pos)
            if tile_idx is not None and tile_idx != self.state.robber_idx:
                tile = self.state.tiles[tile_idx]
                self.state.entangling_pair.append(tile)
                if len(self.state.entangling_pair) == 2:
                    self.state.entangle_pair_of_normal_tiles(self.state.entangling_pair, self.state.unused_ent_group_number)
                    self.state.entangling_pair = []
                    self.state.entangling = False

    def draw(self):
        s = self.screen
        s.fill(BG_COLOR)
        self.state.draw()  # the game state handles low-level drawing

