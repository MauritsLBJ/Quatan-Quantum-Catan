# src/game_state.py
# The central glue: game state, handlers, drawing of board and UI rectangles used by UI

import pygame, math
import random
from .constants import WIN_W, WIN_H, BG_COLOR, PANEL_BG, LINE_COLOR, TEXT_COLOR, WHITE, BLACK, PLAYER_COLORS, HEX_SIZE, BUTTON_COLOR, getFont
from .board import (
    compute_centers_and_polys,
    compute_sea_polys,
    randomize_tiles,
    generate_sea_ring,
    HEX_COORDS,
    SEA_COORDS
)
from .board import compute_centers_and_polys as board_centers_polys
from .board import compute_sea_polys
from .util import hex_to_pixel, polygon_corners, dist
from .dice import roll_with_animation
from .quantum import create_quantum_token_from_tile, collect_from_tile_for_player, measure_token
from .robber import initial_robber_tile, move_robber_to
from .resources import best_trade_ratio_for, perform_trade
from .buildings import compute_vertex_adjacency
from .player import Player
from .constants import WIN_W as W, WIN_H as H

# UI helper - create rects for buttons; draw helpers
def draw_text(screen, text, x, y, size=18, color=TEXT_COLOR):
    font = getFont(size)
    surf = font.render(text, True, color)
    screen.blit(surf, (x, y))

class GameState:
    def __init__(self, num_players=4, screen=None):
        self.screen = screen
        self.num_players = num_players
        self.current_player = 0
        # initialize players
        self.players = [Player(i) for i in range(num_players)]
        for i,p in enumerate(self.players):
            p.color = PLAYER_COLORS[i]
            p.resources = {"wood":2,"brick":2,"sheep":2,"wheat":2,"ore":2}
            p.tokens = []
        # geometry & tiles
        self.origin = (self.screen.get_width()//2, self.screen.get_height()//2 - 10)
        self.centers, self.polys = compute_centers_and_polys(self.origin)
        self.sea_centers, self.sea_polys = compute_sea_polys(self.origin)
        self.tiles = randomize_tiles()
        self.sea_tiles = generate_sea_ring()
        # build graph
        _, self.hex_vertex_indices = compute_centers_and_polys(self.origin)
        self.intersections = []  # create by extracting vertices in build_graphFrom polygons-like manner
        self._build_vertex_list()
        # derived
        self.road_mids = self._compute_road_mids()
        self.roads = self._compute_roads_list()
        # owners
        self.roads_owner = {}  # edge tuple -> player index
        self.settlements_owner = {}  # vertex idx -> (player, type)
        # adjacency for settlement placement
        self.vertex_neighbors = compute_vertex_adjacency(self.hex_vertex_indices)
        # ports map: sea index -> vertex indices it serves
        self.port_vertex_map = self._assign_ports_to_vertices()
        # robber
        self.robber_idx = initial_robber_tile(self.tiles)
        # UI rectangles (placeholders)
        self.reset_rect = pygame.Rect(20,20,120,36)
        self.dice_rect = pygame.Rect(20,70,120,40)
        self.end_turn_rect = pygame.Rect(20, H - 66, 120, 44)
        self.trade_rect = pygame.Rect(W-240, 18, 80, 26)
        # shop rects are computed each draw
        self.shop_rects = []
        self.shop_rects = []
        # trade UI rects placeholders
        self.trade_give_rects = []
        self.trade_recv_rects = []

    # geometry helpers
    def _build_vertex_list(self):
        # create intersections by rounding corners of polygons
        vmap = {}
        idx = 0
        for poly in self.polys:
            for corner in poly:
                key = (round(corner[0],4), round(corner[1],4))
                if key not in vmap:
                    vmap[key] = idx
                    self.intersections.append(corner)
                    idx += 1
        # now compute hex_vertex_indices mapping to vmap indexes
        # reuse earlier logic to find indices
        self.hex_vertex_indices = []
        for poly in self.polys:
            idxs = []
            for corner in poly:
                key = (round(corner[0],4), round(corner[1],4))
                idxs.append(vmap[key])
            self.hex_vertex_indices.append(idxs)

    def _compute_roads_list(self):
        road_set = set()
        for idxs in self.hex_vertex_indices:
            for i in range(6):
                a = idxs[i]; b = idxs[(i+1)%6]
                if a != b:
                    road_set.add(tuple(sorted((a,b))))
        self.roads_list = sorted(list(road_set))
        return self.roads_list

    def _compute_road_mids(self):
        mids = []
        roads = self._compute_roads_list()
        for a,b in roads:
            ax,ay = self.intersections[a]
            bx,by = self.intersections[b]
            mids.append(((ax+bx)/2, (ay+by)/2))
        return mids

    def _compute_road_mids(self):
        # recompute from current intersections and roads
        road_list = self._compute_roads_list()
        mids = []
        for a,b in road_list:
            ax,ay = self.intersections[a]
            bx,by = self.intersections[b]
            mids.append(((ax+bx)/2, (ay+by)/2))
        self.road_list = road_list
        return mids

    def _assign_ports_to_vertices(self):
        mapping = {}
        for i, st in enumerate(self.sea_tiles):
            cx, cy = self.sea_polys[i][0]  # center approx via first vertex of polygon
            # find two nearest intersections
            dists = [(j, math.hypot(ix-cx, iy-cy)) for j, (ix,iy) in enumerate(self.intersections)]
            dists.sort(key=lambda x: x[1])
            picks = [dists[0][0], dists[1][0]]
            mapping[i] = picks
        return mapping

    # gameplay helpers
    def find_nearest_intersection(self, pos, max_dist=48):
        x,y = pos
        best = None
        bd = max_dist
        for i,(ix,iy) in enumerate(self.intersections):
            d = math.hypot(ix-x, iy-y)
            if d < bd:
                bd = d
                best = i
        return best

    def find_nearest_road(self, pos, max_dist=48):
        x,y = pos
        best = None
        bd = max_dist
        roads = self._compute_roads_list()
        for i,(a,b) in enumerate(roads):
            ax,ay = self.intersections[a]; bx,by = self.intersections[b]
            mx,my = (ax+bx)/2, (ay+by)/2
            d = math.hypot(mx-x, my-y)
            if d < bd:
                bd = d
                best = i
        return best

    def can_place_settlement(self, v_idx):
        return v_idx not in self.settlements_owner and all(n not in self.settlements_owner for n in self.vertex_neighbors.get(v_idx, []))

    def can_upgrade_to_city(self, player_idx, v_idx):
        owner = self.settlements_owner.get(v_idx)
        return owner is not None and owner[0] == player_idx and owner[1] == "village"

    def can_place_road_slot(self, road_idx):
        roads = self._compute_roads_list()
        if road_idx is None or road_idx >= len(roads):
            return False
        edge = tuple(roads[road_idx])
        return edge not in self.roads_owner

    def player_can_afford(self, player_idx, item_key):
        # use COSTS mapping minimal (recreate simple mapping)
        COSTS = {
            "road": {"wood":1,"brick":1},
            "village": {"wood":1,"brick":1,"sheep":1,"wheat":1},
            "city": {"wheat":2,"ore":3},
            "dev": {"sheep":1,"wheat":1,"ore":1}
        }
        cost = COSTS.get(item_key, {})
        res = self.players[player_idx].resources
        for k,v in cost.items():
            if res.get(k,0) < v:
                return False
        return True

    def player_buy(self, player_idx, item_key):
        COSTS = {
            "road": {"wood":1,"brick":1},
            "village": {"wood":1,"brick":1,"sheep":1,"wheat":1},
            "city": {"wheat":2,"ore":3},
            "dev": {"sheep":1,"wheat":1,"ore":1}
        }
        if not self.player_can_afford(player_idx, item_key):
            return False
        cost = COSTS[item_key]
        for k,v in cost.items():
            self.players[player_idx].resources[k] -= v
        return True

    def place_settlement(self, v_idx, player_idx, typ="village"):
        self.settlements_owner[v_idx] = (player_idx, typ)
        self.players[player_idx].score += (1 if typ=="village" else 2)

    def upgrade_to_city(self, v_idx, player_idx):
        self.settlements_owner[v_idx] = (player_idx, "city")
        # city gives +1 score relative to village
        self.players[player_idx].score += 1

    def place_road(self, road_idx, player_idx):
        roads = self._compute_roads_list()
        edge = tuple(roads[road_idx])
        self.roads_owner[edge] = player_idx

    def end_turn(self):
        self.current_player = (self.current_player + 1) % self.num_players

    # dice & distribution using quantum tokens
    def roll_and_distribute(self):
        print("Rolling dice and distributing resources...")
        roll = roll_with_animation(self.screen)
        print(f"Dice rolled: {roll}")
        self.last_roll = roll
        # collect tokens or classical resources to players
        # for each tile: if its number matches roll:
        for ti,tile in enumerate(self.tiles):
            if tile.get("number") == roll:
                print(f"Tile at coord: {tile.get("coord")} activated for roll {roll}.")
                # skip robber tile
                if ti == getattr(self, "robber_idx", None):
                    print("Robber present, no resources distributed from this tile.")
                    continue
                # for each adjacent vertex, give token or resource to owner
                for v in self.hex_vertex_indices[ti]:
                    owner = self.settlements_owner.get(v)
                    print(owner)
                    if owner:
                        player_idx, typ = owner
                        if tile.get("quantum", False):
                            print(f"Tile is quantum, giving token to Player {player_idx}.")
                            token = create_quantum_token_from_tile(tile)
                            # store token with player
                            token["from_tile_idx"] = ti
                            self.players[player_idx].tokens.append(token)
                            print(f"all resources of player are now: {self.players[player_idx].resources}. And all tokens of player are now: {self.players[player_idx].tokens}.")
                            print(self.screen, 
                                      #f"{self.players[player_idx]} received one {token.get("type")} token, with resource distribution: {token.get("possible")}., 
                                      "received",
                                      160, 100)
                                    
                        else:
                            # classical payout
                            print(f"Tile is classical, giving resource to Player {player_idx}.")
                            amt = 2 if typ == "city" else 1
                            self.players[player_idx].resources[tile["resource"]] += amt
                            print(f"Player {player_idx} received {amt} of {tile.get("resource")}.")
                            print(f"all resources of player are now: {self.players[player_idx].resources}. And all tokens of player are now: {self.players[player_idx].tokens}.")
                            print(self.screen, f"{self.players[player_idx]} received {amt}: {tile.get("resource")}.", 160, 100)

    # trades
    def perform_trade(self, player_idx, give_resource, receive_resource):
        ratio = best_trade_ratio_for(player_idx, give_resource, self.sea_tiles, self.port_vertex_map, self.settlements_owner)
        ok = perform_trade([p.resources for p in self.players], player_idx, give_resource, receive_resource, ratio)
        return ok, ratio

    # robber movement: puts or breaks quantum state
    def move_robber_here(self, tile_idx):
        affected = move_robber_to(tile_idx, self.tiles, self.settlements_owner)
        self.robber_idx = tile_idx
        return affected

    # switches a pair of normal tiles to a pair of entangeled tiles
    def entangle_pair_of_normal_tiles(self, pair_of_tiles, ent_group_number):
        """ A list with a two pairs needs to be passed in this function, next it checks with which of the 
        tiles in the self.tiles list it matches and changes the atributes of the dictionary belonging to the tile in 
        the self.tiles list, entgroup_number should come from the previous pair of entangled tiles.
        Does assume the tiles are not quantum"""
        # saves the resources of the normal tiles
        resourche1 = pair_of_tiles[0].get("resource")
        resourche2 = pair_of_tiles[1].get("resource")
        # checks for every tile in the self.riles list if one of the given tiles equals it
        for n in range(len(self.tiles)):
            for tile in pair_of_tiles:
                if tile == self.tiles[n]:
                    # changes all the atributes of the tile in self.tiles
                    self.tiles[n]["quantum"] = True
                    self.tiles[n]["ent_group"] = ent_group_number
                    self.tiles[n]["resource"] = None
                    self.tiles[n]["superposed"] = [resourche1, resourche2]
                    if ent_group_number % 2 == 0:
                        self.tiles[n]["correlation"] = 1
                    else:
                        self.tiles[n]["correlation"] = -1

    def unentagle_pair_of_quantum_tiles(self, pair_of_q_tiles):
        """same principle as the other function, assumes the two quantum tiles contained in the list have the 
        same superposition and shit"""
        # gets the superposed list from one of the tiles, other should match so no problem there
        possible_resources = pair_of_q_tiles[0].get("superposed")
        # shuffles the list to create randomness
        random.shuffle(possible_resources)
        # checks for every tile in the self.tiles list if one of the given tiles equals it
        for n in range(len(self.tiles)):
            for tile in pair_of_q_tiles:
                if tile == self.tiles[n]:
                    # changes all the atributes of the tile in self.tiles
                    self.tiles[n]["quantum"] = False
                    self.tiles[n]["ent_group"] = None
                    # gives one tile one of the possible resources, the other the other resource
                    self.tiles[n]["resource"] = possible_resources.pop()
                    del self.tiles[n]["superposed"] 
                    del self.tiles[n]["correlation"]
                    

    # draw everything (board + UI overlays)
    def draw(self):
        s = self.screen
        s.fill(BG_COLOR)

        # sea
        for i, s_tile in enumerate(self.sea_tiles):
            color = (165,190,220) if s_tile.get("port") == "sea" else (150,170,210)
            pygame.draw.polygon(s, color, self.sea_polys[i])
            pygame.draw.polygon(s, LINE_COLOR, self.sea_polys[i], 2)

        # land tiles
        for i, tile in enumerate(self.tiles):
            res = tile.get("resource")
            mapping = {"wood":(120,180,80),"brick":(200,140,100),"sheep":(160,210,140),"wheat":(230,210,100),"ore":(140,140,170),"desert":(230,200,160)}
            if tile.get("quantum", False):
                # quantum tiles: use a special striping fill
                # because of the superposition the resources need to be pulled from the "superposed" part pf tile, next
                #the color value will be paired
                res1 = tile.get("superposed")[0]
                res2 = tile.get("superposed")[1]
                col1 = mapping.get(res1,(200,200,200))
                col2 = mapping.get(res2, (200,200,200))
                # divides the hexagons in half and fills in both halves
                lefthalf_polys = [self.polys[i][1],self.polys[i][2],self.polys[i][3],self.polys[i][4]]
                righthalf_polys = [self.polys[i][4],self.polys[i][5],self.polys[i][0],self.polys[i][1]]
                pygame.draw.polygon(s, col1, righthalf_polys)
                pygame.draw.polygon(s, col2, lefthalf_polys)
                pygame.draw.polygon(s, LINE_COLOR, self.polys[i], 3)

            else:
                col = mapping.get(res, (200,200,200))
                pygame.draw.polygon(s, col, self.polys[i])
                pygame.draw.polygon(s, LINE_COLOR, self.polys[i], 3)
            # draw number
            if tile.get("number") is not None:
                font = getFont(18)
                num_surf = font.render(str(tile["number"]), True, BLACK)
                cx = sum(p[0] for p in self.polys[i]) / 6
                cy = sum(p[1] for p in self.polys[i]) / 6
                # white circle behind
                pygame.draw.circle(s, WHITE, (int(cx), int(cy)), 18)
                s.blit(num_surf, (cx - num_surf.get_width()/2, cy - num_surf.get_height()/2))

        # draw roads
        for (a,b), owner in self.roads_owner.items():
            ax,ay = self.intersections[a]; bx,by = self.intersections[b]
            pygame.draw.line(s, (60,40,20), (ax,ay), (bx,by), 10)
            pygame.draw.line(s, PLAYER_COLORS[owner], (ax,ay), (bx,by), 6)

        # draw settlements
        for idx, (owner, typ) in self.settlements_owner.items():
            x,y = self.intersections[idx]
            col = PLAYER_COLORS[owner]
            if typ == "village":
                pygame.draw.circle(s, col, (int(x), int(y)), 12)
                pygame.draw.circle(s, BLACK, (int(x), int(y)), 2)
            else:
                pygame.draw.rect(s, col, (x-13, y-13, 26, 26))
                pygame.draw.rect(s, BLACK, (x-13, y-13, 26, 26), 2)

        # UI panels (basic)
        # inventory panel
        ix = self.screen.get_width() - 240
        pygame.draw.rect(s, PANEL_BG, (ix, 8, 232, 220), border_radius=8)
        font = getFont(16)
        title = font.render(f"P{self.current_player+1}", True, PLAYER_COLORS[self.current_player])
        s.blit(title, (ix+10, 10))
        sub = getFont(14).render("Inventory:", True, TEXT_COLOR)
        s.blit(sub, (ix+10, 36))
        # show resources
        for i,res in enumerate(["wood","brick","sheep","wheat","ore"]):
            txt = getFont(14).render(f"{res.capitalize()}: {self.players[self.current_player].resources.get(res,0)}", True, TEXT_COLOR)
            s.blit(txt, (ix+12, 60 + i*20))

        # top-left buttons
        pygame.draw.rect(s, BUTTON_COLOR, self.reset_rect, border_radius=8)
        draw_text(s, "Reset", self.reset_rect.x+16, self.reset_rect.y+6, size=18, color=WHITE)
        pygame.draw.rect(s, (100,100,200), self.dice_rect, border_radius=8)
        draw_text(s, "Roll Dice", self.dice_rect.x+12, self.dice_rect.y+8, size=18, color=WHITE)
        pygame.draw.rect(s, (80,150,90), self.end_turn_rect, border_radius=8)
        draw_text(s, "End Turn", self.end_turn_rect.x+12, self.end_turn_rect.y+8, size=18, color=WHITE)

        # shop
        sx, sy = self.screen.get_width()-300, self.screen.get_height()-210
        pygame.draw.rect(s, PANEL_BG, (sx, sy, 240, 180), border_radius=8)
        draw_text(s, "Shop", sx+10, sy+8, size=18)
        # populate shop rects and store them in state
        self.shop_rects = []
        opts = [("road","Road"),("village","Village"),("city","City"),("dev","Dev Card")]
        for i,(k,l) in enumerate(opts):
            r = pygame.Rect(sx+10, sy+40 + i*36, 200, 30)
            pygame.draw.rect(s, BUTTON_COLOR, r, border_radius=6)
            draw_text(s, f"{l}", r.x+8, r.y+6, size=14, color=WHITE)
            self.shop_rects.append((k,r))

        # small dice last roll text
        if hasattr(self, "last_roll") and self.last_roll is not None:
            draw_text(s, f"Dice: {self.last_roll}", 160, 80, size=20)

        # port info overlay small
        # draw port markers
        for i, st in enumerate(self.sea_tiles):
            if st.get("port") != "sea":
                cx = sum(p[0] for p in self.sea_polys[i]) / 6
                cy = sum(p[1] for p in self.sea_polys[i]) / 6
                txt = getFont(12).render(st["port"].replace("port_","").upper(), True, BLACK)
                s.blit(txt, (cx - txt.get_width()/2, cy - txt.get_height()/2))

        # store some UI rects for UI handler
        self.reset_rect = self.reset_rect
        self.dice_rect = self.dice_rect
        self.end_turn_rect = self.end_turn_rect
        self.trade_rect = self.trade_rect
        # trade give/recv rects not implemented fully for compactness
        # (UI handles simplified trade by textual input mapping in main UI class)
        
    def end_turn(self):
        self.current_player = (self.current_player + 1) % self.num_players

    # simple update hook called from main loop
    def update(self, dt):
        """
        dt: milliseconds since last frame.
        Currently a no-op placeholder. Extend this to:
         - advance animations
         - process token timers / measurements
         - handle background game logic
        """
        # Example: if you later add per-player token timers, process them here.
        return
