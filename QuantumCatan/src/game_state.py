# src/game_state.py
# The central glue: game state, handlers, drawing of board and UI rectangles used by UI

import pygame, math, time, os
import random
from .constants import WIN_W, WIN_H, BG_COLOR, PANEL_BG, LINE_COLOR, TEXT_COLOR, WHITE, BLACK, PLAYER_COLORS, BUTTON_COLOR, getFont, PREVIEW_COLOR, ENT_NUMBER_COLOURS
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
from .resources import best_trade_ratio_for, perform_trade
from .rendering import draw_text
from .buildings import compute_vertex_adjacency
#from .robber import initial_robber_tile
from .player import Player
from .constants import WIN_W as W, WIN_H as H

os.chdir(os.path.dirname(os.path.realpath(__file__)))


class GameState:
    def __init__(self, num_players=4, screen=None):
        self.screen = screen
        self.num_players = num_players
        self.playerWon = False
        self.num_entangled_pairs = 0
        self.runningGame = False
        self.hex_size = 50
        self.devMode = False
        self.origin = (self.screen.get_width()//2, self.screen.get_height()//2 - 10)
        self.centers, self.polys = compute_centers_and_polys(self.origin)
        self.sea_centers, self.sea_polys = compute_sea_polys(self.origin)
        self.num_player_buttons = []
        self.entanglement_buttons = []
        self.start_button = pygame.Rect(W//2 - 90, H//2 + 250, 180, 40)
        self.restart_button = pygame.Rect(W//2 - 105, H//2 + 200, 210, 40)
        

    def start_game(self,):
        self.runningGame = True
        self.reset_game()
    

    # -- messaging helpers ---------------------------------------
    def push_message(self, text, duration_ms=10000):
        """
        Add a transient on-screen message. Rendered by draw().
        """
        if not text:
            return
        expires = pygame.time.get_ticks() + duration_ms
        self.message_log.append((text, expires))
        # keep it bounded
        if len(self.message_log) > 20:
            self.message_log.pop(0)

    def _prune_messages(self):
        now = pygame.time.get_ticks()
        self.message_log = [(t,e) for (t,e) in self.message_log if e > now]


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
        #print (self.roads_list)
        return self.roads_list


    def _compute_road_mids(self):
        # recompute from current intersections and roads
        road_list = self._compute_roads_list()
        mids = []
        for a,b in road_list:
            ax,ay = self.intersections[a]
            bx,by = self.intersections[b]
            mids.append(((ax+bx)/2, (ay+by)/2))
        self.road_list = road_list
        #print(mids)
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

    def find_nearest_tile(self, pos, max_dist=60):
        """
        Returns the index of the tile whose center is closest to the mouse position.
        If no tile is within max_dist pixels, returns None.
        """
        x, y = pos
        best_idx = None
        dist = max_dist

        for i, (cx, cy) in enumerate(self.centers):
            d = math.hypot(cx - x, cy - y)
            if d < dist:
                dist = d
                best_idx = i

        return best_idx

    def can_place_settlement(self, v_idx):
        # check adjacent roads
        if v_idx not in self.settlements_owner and all(n not in self.settlements_owner for n in self.vertex_neighbors.get(v_idx, [])):
            if self.round >= 2 and self.devMode == False:
                for neighbor in self.vertex_neighbors.get(v_idx, []):
                    adjacent_edge = tuple(sorted((v_idx, neighbor)))
                    if adjacent_edge in self.roads_owner and self.roads_owner[adjacent_edge] == self.current_player:
                        return True
            else:
                return True
        return False

    def can_upgrade_to_city(self, player_idx, v_idx):
        owner = self.settlements_owner.get(v_idx)
        return owner is not None and owner[0] == player_idx and owner[1] == "settlement"

    def can_place_road_slot(self, road_idx):
        roads = self._compute_roads_list()
        if road_idx is None or road_idx >= len(roads):
            return False
        edge = tuple(roads[road_idx])
        #print(edge)
        #check if adjacent to existing road or settlement of current player
        if self.round >=2:
            if edge not in self.roads_owner:
                for vertex in edge:
                    # check adjacent settlements
                    owner = self.settlements_owner.get(vertex)
                    if owner is not None and owner[0] == self.current_player:
                        return True
                    # check adjacent roads
                    for neighbor in self.vertex_neighbors.get(vertex, []):
                        adjacent_edge = tuple(sorted((vertex, neighbor)))
                        if adjacent_edge in self.roads_owner and self.roads_owner[adjacent_edge] == self.current_player:
                            return True
                return False
            else: return False
        else:
            if edge not in self.roads_owner:
                for vertex in edge:
                    owner = self.settlements_owner.get(vertex)
                    if owner is not None and vertex == self.last_settlement_pos and owner[0] == self.current_player:
                        return True
        return False

    def player_can_afford(self, player_idx, item_key):
        # use COSTS mapping minimal (recreate simple mapping)
        COSTS = {
            "road": {"lumber":1,"brick":1},
            "settlement": {"lumber":1,"brick":1,"wool":1,"grain":1},
            "city": {"grain":2,"ore":3},
            "dev": {"wool":1,"grain":1,"ore":1}
        }
        cost = COSTS.get(item_key, {})
        res = self.players[player_idx].resources
        for k,v in cost.items():
            if res.get(k,0) < v:
                return False
        return True

    def player_buy(self, player_idx, item_key):
        COSTS = {
            "road": {"lumber":1,"brick":1},
            "settlement": {"lumber":1,"brick":1,"wool":1,"grain":1},
            "city": {"grain":2,"ore":3},
            "dev": {"wool":1,"grain":1,"ore":1}
        }
        if not self.player_can_afford(player_idx, item_key):
            return False
        cost = COSTS[item_key]
        for k,v in cost.items():
            self.players[player_idx].resources[k] -= v
        return True

    def place_settlement(self, v_idx, player_idx, typ="settlement"):
        self.push_message(f"{self.players[player_idx].name} placed a settlement.")
        self.settlements_owner[v_idx] = (player_idx, typ)
        self.last_settlement_pos = v_idx
        self.players[player_idx].buildables_placed["settlements"].append(v_idx)
        self.players[player_idx].score += (1 if typ=="settlement" else 2)

    def upgrade_to_city(self, v_idx, player_idx):
        self.push_message(f"{self.players[player_idx].name} placed a city.")
        self.settlements_owner[v_idx] = (player_idx, "city")
        self.players[player_idx].buildables_placed["cities"].append(v_idx)
        # city gives +1 score relative to settlement
        self.players[player_idx].score += 1

    def place_road(self, road_idx, player_idx):
        self.push_message(f"{self.players[player_idx].name} placed a road.")
        roads = self._compute_roads_list()
        edge = tuple(roads[road_idx])
        self.roads_owner[edge] = player_idx
        self.players[player_idx].buildables_placed["roads"].append(road_idx)
        
        #check longest road update
        roads_in_road = [edge]
        longest_road = 1
        for vertex in edge:
            self.find_longest_road(vertex, roads_in_road, longest_road, player_idx)

        
        
        
    def find_longest_road(self, vertex, roads_in_road, longest_road, player_idx):
        for neighbor in self.vertex_neighbors.get(vertex, []):
            adjacent_edge = tuple(sorted((vertex, neighbor)))
            if adjacent_edge in self.roads_owner and self.roads_owner[adjacent_edge] == self.current_player and adjacent_edge not in roads_in_road:
                roads_in_road.append(adjacent_edge)
                for v in adjacent_edge:
                    if v != vertex:
                        self.find_longest_road(v, roads_in_road, longest_road, player_idx)
                        roads_in_road.pop()
            else:
                if len(roads_in_road) > longest_road:
                    longest_road = len(roads_in_road)
        if longest_road >= 5:
            if self.longest_road is None or longest_road > self.longest_road[1]:
                if self.longest_road is not None and self.longest_road[0] == player_idx:
                    self.push_message(f"{self.players[player_idx].name} has increased their Longest Road to length {longest_road}!")
                elif self.longest_road is not None:
                    prev_player_idx = self.longest_road[0]
                    self.push_message(f"{self.players[player_idx].name} takes Longest Road from {self.players[prev_player_idx].name} with length {longest_road}!")
                    self.players[prev_player_idx].score -= 2
                    self.players[player_idx].score += 2
                else:
                    self.push_message(f"{self.players[player_idx].name} has claimed Longest Road with length {longest_road}!")
                    self.players[player_idx].score += 2
                self.longest_road = (player_idx, longest_road)
                
        
    def give_initial_settlement_resources(self, v_idx, player_idx):
        # give resources from adjacent tiles to player
        adjacent_tiles = []
        for ti, hex_vidxs in enumerate(self.hex_vertex_indices):
            if v_idx in hex_vidxs:
                adjacent_tiles.append(ti)
        for ti in adjacent_tiles:
            tile = self.tiles[ti]
            res = tile.get("resource")
            print(res)
            if res and res != "desert":
                self.players[player_idx].resources[res] += 1
                self.push_message(f"{self.players[player_idx].name} received 1 {res} from initial settlement.")
            if tile.get("quantum", False):
                token = {"type":"entangled","group":tile["ent_group"], "possible": tile.get("superposed")[:], "tile_coord": tile["coord"]}
                token["from_tile_idx"] = ti
                self.players[player_idx].tokens.append(token)
                self.push_message(f"{self.players[player_idx].name} received one superposed token from initial settlement.")

    # dice & distribution using quantum tokens
    def roll_and_distribute(self, number):
        #print("Rolling dice and distributing resources...")
        self.moving_robber = False
        self.activated_settlements = []
        if self.devMode == False: self.allowed_actions.remove("rolling")
        roll = 0
        self.milliseconds_passed_at_roll = self.milliseconds_passed
        if number == None: 
            roll = random.randint(1,6) + random.randint(1,6) 
        else: 
            roll = int(number)
        self.push_message(f"Dice rolled: {roll}")
        self.last_roll = roll
        if roll == 7:
            self.push_message("Please move the robber.")
            self.moving_robber = True
            if self.devMode == False: 
                for k in self.allowed_actions:
                    self.allowed_actions.remove(k)
            return
        else:
            if self.devMode == False: 
                for k in ("endTurn", "trading", "building"):
                    self.allowed_actions.append(k)

        # collect tokens or classical resources to players
        # for each tile: if its number matches roll:
        for ti,tile in enumerate(self.tiles):
            if tile.get("number") == roll:
                #print(f"Tile at coord: {tile.get("coord")} activated for roll {roll}.")
                # skip robber tile
                if ti == getattr(self, "robber_idx", None):
                    #print("Robber present, no resources distributed from this tile.")
                    continue
                # for each adjacent vertex, give token or resource to owner
                for v in self.hex_vertex_indices[ti]:
                    owner = self.settlements_owner.get(v)
                    #print(owner)
                    if owner:
                        player_idx, typ = owner
                        amt = 2 if typ == "city" else 1
                        if typ == "settlement": self.activated_settlements.append(v)
                        else: self.activated_cities.append(v)
                        if tile.get("quantum", False):
                            #print(f"Tile is quantum, giving token to Player {player_idx}.")
                            token = {"type":"entangled","group":tile["ent_group"], "possible": tile.get("superposed")[:], "tile_coord": tile["coord"]}
                            # store token with player
                            token["from_tile_idx"] = ti
                            for k in range(amt):
                                self.players[player_idx].tokens.append(token)
                                #print(f"all resources of player are now: {self.players[player_idx].resources}. And all tokens of player are now: {self.players[player_idx].tokens}.")
                                self.push_message(f"{self.players[player_idx].name} received one superposed token")
                                #print(self.players[player_idx].tokens)
                                    
                        else:
                            # classical payout
                            #print(f"Tile is classical, giving resource to Player {player_idx}.")
                            
                            self.players[player_idx].resources[tile["resource"]] += amt
                            #print(f"Player {player_idx} received {amt} of {tile.get("resource")}.")
                            #print(f"all resources of player are now: {self.players[player_idx].resources}. And all tokens of player are now: {self.players[player_idx].tokens}.")
                            self.push_message(f"{self.players[player_idx].name} received {amt}: {tile.get("resource")}.")

    # trades
    def perform_trade(self, player_idx, give_resource, receive_resource):
        ratio = best_trade_ratio_for(player_idx, give_resource, self.sea_tiles, self.port_vertex_map, self.settlements_owner)
        ok = perform_trade([p.resources for p in self.players], player_idx, give_resource, receive_resource, ratio)
        return ok, ratio
    
    def steal_from_victim(self, thief_idx, victim_idx):
        victim = self.players[victim_idx]
        thief = self.players[thief_idx]
        # gather all resources of victim
        available_resources = [res for res, amt in victim.resources.items() if amt > 0]
        if not available_resources:
            self.push_message(f"{victim.name} has no resources to steal.")
            return
        stolen_resource = random.choice(available_resources)
        victim.resources[stolen_resource] -= 1
        thief.resources[stolen_resource] += 1
        for k in ("endTurn", "trading", "building", "placeDevCard"):
            self.allowed_actions.append(k)
        self.push_message(f"{thief.name} stole 1 {stolen_resource} from {victim.name}.")

    # robber movement: puts or breaks quantum state
    def move_robber_to(self, tile_idx):
        t = self.tiles[tile_idx]
        self.robber_idx = tile_idx
        if t.get("quantum", False) and t.get("ent_group") is not None:
            self.unentangle_pair_of_quantum_tiles(t)
            self.push_message(f"Robber moved to entangled quantum tile at index {tile_idx}, unentangling the pair.")
            self.push_message("Now entangle a pair of normal tiles.")
            self.entangling = True
        else:
            if self.devMode == False:
                for n in ("endTurn", "trading", "building", "placeDevCard"):
                    self.allowed_actions.append(n)
        #check if another player is on this tile and steal a resource
        for v in self.hex_vertex_indices[tile_idx]:
            owner = self.settlements_owner.get(v)
            if owner and self.current_player not in owner:
                owner_idx, btype = owner
                if owner_idx not in self.possible_victims:
                    self.possible_victims.append(owner_idx)
    # switches a pair of normal tiles to a pair of entangeled tiles
    def entangle_pair_of_normal_tiles(self, pair_of_tiles, ent_group_number, start=False):
        """ A list with a two pairs needs to be passed in this function, next it checks with which of the 
        tiles in the self.tiles list it matches and changes the atributes of the dictionary belonging to the tile in 
        the self.tiles list, entgroup_number should come from the previous pair of entangled tiles.
        Does assume the tiles are not quantum"""
        
        if self.devMode == False and start == False:
            for n in ("endTurn", "trading", "building", "placeDevCard"):
                self.allowed_actions.append(n)
        # saves the resources of the normal tiles
        resource1 = pair_of_tiles[0][1].get("resource")
        resource2 = pair_of_tiles[1][1].get("resource")
        # checks for every tile in the self.riles list if one of the given tiles equals it
        for n in range(len(self.tiles)):
            for idx, tile in pair_of_tiles:
                if tile == self.tiles[n]:
                    # changes all the atributes of the tile in self.tiles
                    self.tiles[n]["quantum"] = True
                    self.tiles[n]["ent_group"] = ent_group_number
                    self.tiles[n]["resource"] = None
                    self.tiles[n]["distribution"] = 0.5
                    self.tiles[n]["superposed"] = [resource1, resource2]

    def unentangle_pair_of_quantum_tiles(self, robber_tile):
        """same principle as the other function, assumes the two quantum tiles contained in the list have the 
        same superposition and shit"""
        # gets a list of the tiles which will change
        pair_of_q_tiles = []
        ent_group_number = robber_tile.get("ent_group")
        #print(ent_group_number)
        for tile in self.tiles:
            if tile.get("ent_group") == ent_group_number:
                    pair_of_q_tiles.append(tile)
        # gets the superposed list from one of the tiles, other should match so no problem there            
        possible_resources = robber_tile.get("superposed")[:]
        possible_resources_lesser_dis = possible_resources[:]
        possible_resources_greater_dis = possible_resources[:]
        # modifies the possible resources to account for the distribution, by adding the first resourche a couple times
        n = pair_of_q_tiles[0].get("distribution") / pair_of_q_tiles[1].get("distribution")
        if n < 1:
            amount_of_most_res = round(1/n)
        else:
            amount_of_most_res = round(n)
        for i in range(amount_of_most_res - 1):
            possible_resources_greater_dis.append(possible_resources_greater_dis[0])
            possible_resources_lesser_dis.append(possible_resources_lesser_dis[1])

        # shuffles the lists to create randomness   
        random.shuffle(possible_resources_lesser_dis)
        random.shuffle(possible_resources_greater_dis)

        # idk MAURITS ZET NOTITIES NEER
        self.unused_ent_group_numbers.append(ent_group_number)
        
        # checks for every tile in the self.tiles list if one of the given tiles equals it
        already_used_resource = None
        for n in range(len(self.tiles)):
            for tile in pair_of_q_tiles:
                if tile == self.tiles[n]:
                    # changes all the atributes of the tile in self.tiles
                    self.tiles[n]["quantum"] = False
                    self.tiles[n]["ent_group"] = None
                    # gives one tile one of the possible resources, the other the other resource
                    if already_used_resource == None:
                        if self.tiles[n].get("distribution") >= 0.49:
                            already_used_resource = possible_resources_greater_dis.pop()
                        else:
                            already_used_resource = possible_resources_lesser_dis.pop()
                        self.tiles[n]["resource"] = already_used_resource
                    else:
                        possible_res = possible_resources.pop()
                        # makes sure the resource is different from the one already used 
                        while possible_res == already_used_resource:
                            possible_res = possible_resources.pop()
                        self.tiles[n]["resource"] = possible_res
                    del self.tiles[n]["superposed"]
                    del self.tiles[n]["distribution"]
        for player in self.players:
            # checks all tokens of every player
            for token in player.tokens[:]:
                # if the token belonged to one of the unentangled tiles, it is removed
                if token.get("group") == ent_group_number:
                    #print(f"Token from tile {token.get("tile_coord")} belonging to entangled group {ent_group_number} has collapsed and is converted from Player {player.idx}'s inventory.")
                    msg = player.add_resource(self.tiles[token.get("from_tile_idx")].get("resource"), self.screen)
                    self.push_message(msg)
                    player.tokens.remove(token)
                    
    def change_ditribution(self, chosen_tile):
        """input the tile which's distribution will increase, this function will increase it's distribution
        and decrease its pair's"""
        # finding both tiles and putting them in a list, also getting the index of the tile which will increase
        group_id = chosen_tile.get("ent_group")
        both_tiles = []
        increase_tile_idx = None
        for tile in self.tiles:
            if tile.get("ent_group") == group_id:
                both_tiles.append(tile) 
                if tile == chosen_tile:
                    increase_tile_idx = len(both_tiles) - 1
        # finding the tile with the lesser distribution and extracting this
        if both_tiles[0].get("distribution") <= both_tiles[1].get("distribution"):
            lesser_idx = 0
        else:
            lesser_idx = 1
        lesser_prob = both_tiles[lesser_idx].get("distribution")
        # really smart way of changing the distribution values by finding through which number  
        probnum = round(1/lesser_prob)
        if probnum != 2:
            for n in range(len(self.tiles)):    
                for i,tile in enumerate(both_tiles):
                    # the tile were are about to change is the tile which will increase in distribution
                    if both_tiles[i] == self.tiles[n] and i == increase_tile_idx:
                        if increase_tile_idx == lesser_idx:
                            self.tiles[n]["distribution"] = (1 / (probnum -1))
                        else:
                            self.tiles[n]["distribution"] = ((probnum) / (probnum + 1))
                    # the tile we're about to change will decrease in distribution
                    elif both_tiles[i] == self.tiles[n]:
                        if increase_tile_idx == lesser_idx:
                            self.tiles[n]["distribution"] = ((probnum-2) / (probnum -1))
                        else:       
                            self.tiles[n]["distribution"] = (1/(probnum + 1))   
        # its the first time getting changed so both distribution values are 0.5          
        else:
            for n in range(len(self.tiles)):    
                for i,tile in enumerate(both_tiles):
                    if both_tiles[i] == self.tiles[n] and i == increase_tile_idx:
                        self.tiles[n]["distribution"] = probnum/(probnum+1)
                    elif both_tiles[i] == self.tiles[n]:
                        self.tiles[n]["distribution"] = (1/(probnum+1))


        


    # draw everything (board + UI overlays)
    def draw(self):
        s = self.screen
        s.fill(BG_COLOR)
        # store some UI rects for UI handler
        self.reset_rect = self.reset_rect
        self.dice_rect = self.dice_rect
        self.trade_rect = self.trade_rect
        self.hex_size = 50 
        self.origin = (self.screen.get_width()//2, self.screen.get_height()//2 - 10)
        self.centers, self.polys = compute_centers_and_polys(self.origin, self.hex_size)
        self.sea_centers, self.sea_polys = compute_sea_polys(self.origin, self.hex_size)
        self.intersections = []
        self._build_vertex_list()
        
        #s.blit(self.bgImage, (0,0))    
        # sea
        for i, s_tile in enumerate(self.sea_tiles):
            color = (165,190,220) if s_tile.get("port") == "sea" else (150,170,210)
            pygame.draw.polygon(s, color, self.sea_polys[i])
            pygame.draw.polygon(s, LINE_COLOR, self.sea_polys[i], 2)

        # land tiles
        for i, tile in enumerate(self.tiles):
            res = tile.get("resource")
            mapping = {"lumber":(120,180,80),"brick":(200,140,100),"wool":(160,210,140),"grain":(230,210,100),"ore":(140,140,170),"desert":(230,200,160)}
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
        for tile in self.tiles:
            if tile.get("quantum", False):
                for i, t in enumerate(self.tiles):
                    if t.get("ent_group") == tile.get("ent_group"):
                        cx, cy = self.centers[i]
                        group = t.get("ent_group")
                        colour = ENT_NUMBER_COLOURS[group - 1]
                        pygame.draw.circle(s, colour, (int(cx), int(cy)), 20, width=4)

        # draw roads
        for (a,b), owner in self.roads_owner.items():
            ax,ay = self.intersections[a]; bx,by = self.intersections[b]
            pygame.draw.line(s, (60,40,20), (ax,ay), (bx,by), 10)
            pygame.draw.line(s, PLAYER_COLORS[owner], (ax,ay), (bx,by), 6)

        # draw settlements
        for idx, (owner, typ) in self.settlements_owner.items():
            x,y = self.intersections[idx]
            col = PLAYER_COLORS[owner]
            deltaseconds = (self.milliseconds_passed - self.milliseconds_passed_at_roll)/1000.0
            if typ == "settlement":
                pygame.draw.circle(s, col, (int(x), int(y)), 12)
                pygame.draw.circle(s, BLACK, (int(x), int(y)), 2)
                if deltaseconds < 0.5 and idx in self.activated_settlements:
                    pygame.draw.circle(s, (255, 255, 0), (int(x), int(y)), 12, width=3)
                elif deltaseconds >= 0.5 and deltaseconds < 1 and idx in self.activated_settlements:
                    pygame.draw.circle(s, col, (int(x) + (self.screen.get_width()-200-int(x))/0.5*(deltaseconds-0.5), int(y) - (int(y)-100)/0.5*(deltaseconds-0.5)), 12)


            else: # city
                pygame.draw.rect(s, col, (x-13, y-13, 26, 26))
                pygame.draw.rect(s, BLACK, (x-13, y-13, 26, 26), 2)
                if deltaseconds < 0.5 and idx in self.activated_cities:
                    pygame.draw.rect(s, (255, 255, 0), (x-13, y-13, 26, 26), width=3)
                if deltaseconds >= 0.5 and deltaseconds < 1 and idx in self.activated_cities:
                    pygame.draw.rect(s, col, (int(x) + (self.screen.get_width()-200-int(x))/0.5*(deltaseconds-0.5), int(y) - (int(y)-100)/0.5*(deltaseconds-0.5), 26, 26))
                
        # draw placement preview
        if self.placing and self.sel:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            if self.sel in ("settlement","city"):
                nearest = self.find_nearest_intersection((mouse_x, mouse_y))
                can_place = self.can_place_settlement(nearest) if self.sel == "settlement" else self.can_upgrade_to_city(self.current_player, nearest)
                #print(can_place)
                if nearest is not None:
                    vx, vy = self.intersections[nearest]
                    if self.sel == "settlement":
                        pygame.draw.circle(s, PREVIEW_COLOR["good" if can_place else "bad"], (int(vx), int(vy)), 12, width=2)
                    else:
                        pygame.draw.rect(s, PREVIEW_COLOR["good" if can_place else "bad"], (vx-13, vy-13, 26, 26), width=2)
            elif self.sel == "road":
                nearest = self.find_nearest_road((mouse_x, mouse_y))
                can_place = self.can_place_road_slot(nearest)
                if nearest is not None:
                    a,b = self.roads_list[nearest]
                    ax,ay = self.intersections[a]; bx,by = self.intersections[b]
                    pygame.draw.line(s, PREVIEW_COLOR["good" if can_place else "bad"], (ax,ay), (bx,by), 6)

        # UI panels (basic)
        
        # inventory panel
        ix = self.screen.get_width() - 240
        #s.blit(self.board, (ix-68, -80))
        pygame.draw.rect(s, PANEL_BG, (ix, 5, 235, 330), border_radius=8)
        font = getFont(16)
        title = font.render(f"P{self.current_player+1}  (Score = {self.players[self.current_player].score})", True, PLAYER_COLORS[self.current_player])
        #f"You have longest road of: {self.longest_road[1]} long" if self.longest_road is not None and self.longest_road[0] == self.current_player else ""
        s.blit(title, (ix+10, 10))
        sub = getFont(16).render("Inventory:", True, TEXT_COLOR)
        s.blit(sub, (ix+10, 36))
        # show resources
        for i,res in enumerate(["lumber","brick","wool","grain","ore"]):
            txt = getFont(14).render(f"{res.capitalize()}: {self.players[self.current_player].resources.get(res,0)}", True, TEXT_COLOR)
            s.blit(txt, (ix+12, 60 + i*20))
        # show tokens
        tokensMessage = getFont(16).render(f"Tokens: ({len(self.players[self.current_player].tokens)})" + f"(18 shown)" if len(self.players[self.current_player].tokens)>18 else f"Tokens: ({len(self.players[self.current_player].tokens)})", True, TEXT_COLOR)
        s.blit(tokensMessage, (ix+12, 170))
        for i, token in enumerate(self.players[self.current_player].tokens if len(self.players[self.current_player].tokens)<=18 else self.players[self.current_player].tokens[-18:]):
            dis = token.get("distribution", 0.5)
            possibleOne = str(token.get("possible")[0])
            possibleTwo = str(token.get("possible")[1])
            size = 14
            distance = 20
            if len(self.players[self.current_player].tokens) > 6:
                size = 12
                distance = 16
                if len(self.players[self.current_player].tokens) > 9:
                    size = 10
                    distance = 12
                    if len(self.players[self.current_player].tokens) > 12:
                        size = 8
                        distance = 8
            txt = getFont(size).render(f"{possibleOne.capitalize()}: {dis}, {possibleTwo.capitalize()}: {1-dis}", True, TEXT_COLOR)
            s.blit(txt, (ix+12, 190 + i*distance))
        
        #trading / robber stealing panel
        if self.possible_victims or self.trading:
            pygame.draw.rect(s, PANEL_BG, (ix, 360, 235, 120), border_radius=8)
            if self.possible_victims:
                draw_text(s, "Steal from:", ix+10, 365, size=16)
                for i, pidx in enumerate(self.possible_victims):
                    self.possible_victims_rects.append(pygame.Rect(ix+10, 390 + i*20, 215, 18))
                    pygame.draw.rect(s, self.players[pidx].color, self.possible_victims_rects[i], border_radius=6)
                    draw_text(s, f"{self.players[pidx].name}", ix+12, 388 + i*20, size=14, color=WHITE)
            elif self.trading:
                draw_text(s, "Trade with:", ix+10, 365, size=16)
                k = 0
                self.possible_trading_partners.append("bank/port")
                self.trading_partners_rects.append(pygame.Rect(ix+10, 390 + k*20, 215, 18))
                pygame.draw.rect(s, WHITE, self.trading_partners_rects[k], border_radius=6)
                draw_text(s, f"Bank/port", ix+12, 388 + k*20, size=14, color=BLACK)
                for i in range(len(self.players)):
                    if i == self.current_player:
                        continue
                    else:
                        self.possible_trading_partners.append(self.players[i].idx)
                        self.trading_partners_rects.append(pygame.Rect(ix+10, 390 + (k+1)*20, 215, 18))
                        pygame.draw.rect(s, self.players[i].color, self.trading_partners_rects[k+1], border_radius=6)
                        draw_text(s, f"{self.players[i].name}", ix+12, 388 + (k+1)*20, size=14, color=WHITE)
                        k+=1
        #trading button:
        self.trade_rect = pygame.Rect(self.screen.get_width() - 190, 340, 80, 20)
        pygame.draw.rect(s, ((150,100,200) if "trading" in self.allowed_actions  or self.devMode == True else (128, 128, 128)), self.trade_rect, border_radius=6)
        draw_text(s, "Trade", self.trade_rect.x+16, self.trade_rect.y+2, size=14, color=WHITE)
        
        # top-left buttons
        pygame.draw.rect(s, BUTTON_COLOR, self.reset_rect, border_radius=8)
        draw_text(s, "Reset", self.reset_rect.x+16, self.reset_rect.y+6, size=18, color=WHITE)
        pygame.draw.rect(s, ((100,100,200) if "rolling" in self.allowed_actions or self.devMode == True else (128, 128, 128)) , self.dice_rect, border_radius=8)
        draw_text(s, "Roll Dice", self.dice_rect.x+12, self.dice_rect.y+8, size=18, color=WHITE)
        self.devMode_rect = pygame.Rect(150, 20, 120, 40)
        if self.devMode == False: pygame.draw.rect(s, (150, 110, 160), self.devMode_rect, border_radius=8)
        if self.devMode == False: draw_text(s, "DevMode", self.devMode_rect.x+12, self.devMode_rect.y+8, size=18, color=WHITE)
        
        self.inspect_rect = pygame.Rect(280, 20, 120, 40)
        pygame.draw.rect(s,  (150*1.2, 110*1.2, 160*1.2)if self.inspecting else (150, 110, 160), self.inspect_rect, border_radius=8)
        draw_text(s, "Inspect", self.inspect_rect.x+12, self.inspect_rect.y+8, size=18, color=WHITE)
        
        #End Turn button
        self.end_turn_rect = pygame.Rect(20, self.screen.get_size()[1] - 66, 120, 44)
        pygame.draw.rect(s, ((80,150,90) if "endTurn" in self.allowed_actions or self.devMode == True else (128, 128, 128)), self.end_turn_rect, border_radius=8)
        draw_text(s, "End Turn", self.end_turn_rect.x+12, self.end_turn_rect.y+8, size=18, color=WHITE)
        
        
        #Title
        draw_text(s, "Quantum Catan", self.screen.get_width()//2, 10, size=24, color=TEXT_COLOR, centered=True)


        # shop
        sx, sy = self.screen.get_width()-245, self.screen.get_height()-210
        pygame.draw.rect(s, PANEL_BG, (sx, sy, 240, 180), border_radius=8)
        draw_text(s, "Shop", sx+10, sy+8, size=18)
        # populate shop rects and store them in state
        self.shop_rects = []
        opts = [("road","Road (1L, 1B)"),("settlement","Settlement (1L, 1B, 1W, 1G)"),("city","City (2G, 3O)"),("dev","Dev Card (1W, 1G, 1O)")]
        selectBrightFactor = 1.2
        hoverBrightFactor = 1.1
        
        self.required_placed = self.num_players*self.round + self.current_player+1
         
        for i,(k,l) in enumerate(opts):
            r = pygame.Rect(sx+10, sy+40 + i*36, 200, 30)
            colour = (128, 128, 128)
            
            if self.round < 2:
                if k == "settlement":
                    if self.settlements_placed == 0:
                        colour = self.players[self.current_player].color
                        if r.collidepoint(pygame.mouse.get_pos()):
                            colour = tuple([hoverBrightFactor*x for x in self.players[self.current_player].color])
                elif k == "road":
                    if self.settlements_placed == 1:
                        if self.roads_placed == 0:
                            colour = self.players[self.current_player].color
                            if r.collidepoint(pygame.mouse.get_pos()):
                                colour = tuple([hoverBrightFactor*x for x in self.players[self.current_player].color])
            elif self.player_can_afford(self.current_player, k):
                if "building" in self.allowed_actions or self.devMode == True:
                    colour = self.players[self.current_player].color
                    if r.collidepoint(pygame.mouse.get_pos()):
                        colour = tuple([hoverBrightFactor*x for x in self.players[self.current_player].color])
            
            if self.sel == k:
                colour = tuple([selectBrightFactor*x for x in self.players[self.current_player].color])
                    
            pygame.draw.rect(s, colour, r, border_radius=6)
            draw_text(s, f"{l}", r.x+8, r.y+6, size=14, color=WHITE)
            self.shop_rects.append((k,r))

        # small dice last roll text
        if hasattr(self, "last_roll") and self.last_roll is not None:
            draw_text(s, f"Dice: {self.last_roll}", 160, 70, size=18)

        # port info overlay small
        # draw port markers
        for i, st in enumerate(self.sea_tiles):
            if st.get("port") != "sea":
                cx = sum(p[0] for p in self.sea_polys[i]) / 6
                cy = sum(p[1] for p in self.sea_polys[i]) / 6
                txt = getFont(12).render(st["port"].replace("port_","").upper(), True, BLACK)
                s.blit(txt, (cx - txt.get_width()/2, cy - txt.get_height()/2))
        
        #draw robber
        if self.robber_idx is not None:
            cx, cy = self.centers[self.robber_idx]
            pygame.draw.circle(s, BLACK, (int(cx), int(cy)), 24, width=8)

        

        # trade give/recv rects not implemented fully for compactness
        # (UI handles simplified trade by textual input mapping in main UI class)
        
        if self.moving_robber or self.entangling or self.inspecting:
            text = None
            if self.inspecting:
                text = "Select a tile to inspect"
            elif self.moving_robber:
                text = "Select a tile for the robber"
            elif self.entangling:
                text = "Select two tiles to entangle"
            
            draw_text(s, text, self.screen.get_width()//2, 50, size=19, color=TEXT_COLOR, centered=True)
            
            # make the borders of selected tile thicker
            mouse_x, mouse_y = pygame.mouse.get_pos()
            hovered_tile = self.find_nearest_tile((mouse_x, mouse_y))
            
            if hovered_tile is not None:
                cx, cy = self.centers[hovered_tile]
                pygame.draw.polygon(s, (255, 255, 0), self.polys[hovered_tile], 3)
            if self.entangling and len(self.entangling_pair) == 1:
                q, r = self.entangling_pair[0][1]["coord"]
                selected_tile = self.entangling_pair[0][0]
                self.unused_ent_group_numbers.sort()
                pygame.draw.polygon(s, ENT_NUMBER_COLOURS[self.unused_ent_group_numbers[0]-1], self.polys[selected_tile], 5)
                
            
        #if self.moving_robber or 
                # draw transient messages (top-center area under title)
        self._prune_messages()
        if self.message_log:
            # draw up to message_max newest messages (latest at bottom)
            to_draw = self.message_log[-self.message_max:]
            start_x = 10
            start_y = 130
            for i, (text, expiry) in enumerate(to_draw):
                # fade based on remaining time
                remaining = expiry - pygame.time.get_ticks()
                alpha = max(0, min(255, int(255 * (remaining / 4000.0))))
                # create a temporary surface to render text with alpha
                font = getFont(14)
                surf = font.render(text, True, TEXT_COLOR)
                # optionally add a semi-transparent background
                bg = pygame.Surface((surf.get_width()+8, surf.get_height()+4), pygame.SRCALPHA)
                bg.fill((BG_COLOR))
                s.blit(bg, (start_x-4, start_y + i*20 - 2))
                s.blit(surf, (start_x, start_y + i*20))

    
    def draw_start_screen(self):
        s = self.screen
        s.fill(BG_COLOR)
        W = self.screen.get_width()
        H = self.screen.get_height()
        self.num_player_buttons = []
        self.entanglement_buttons = []
        self.start_button = self.start_button
        draw_text(s, "Quantum Catan", W//2, H//4, size=48, color=TEXT_COLOR, centered=True)
        draw_text(s, "Select number of players:", W//2, H//2 - 40, size=24, color=TEXT_COLOR, centered=True)
        # draw buttons for 2-4 players
        for i in range(2,5):
            if self.num_players == i:
                button_color = (100, 200, 100)
            else:
                button_color = BUTTON_COLOR
            r = pygame.Rect(W//2 - 105 + (i-2)*70, H//2 + 10, 60, 40)
            pygame.draw.rect(s, button_color, r, border_radius=8)
            draw_text(s, str(i), r.x + 22, r.y + 8, size=24, color=WHITE)
            self.num_player_buttons.append((i,r))
        draw_text(s, "Select number of entanglements:", W//2, H//2 + 80, size=24, color=TEXT_COLOR, centered=True)
        for i in range(1,10):
            if self.num_entangled_pairs == i:
                button_color = (100, 200, 100)
            else:
                button_color = BUTTON_COLOR
            r = pygame.Rect(W//2 - 315 + (i-1)*70, H//2 + 130, 60, 40)
            pygame.draw.rect(s, button_color, r, border_radius=8)
            draw_text(s, str(i), r.x + 22, r.y + 8, size=24, color=WHITE)
            self.entanglement_buttons.append((i,r))
        draw_text(s, "Click start button to start the game.", W//2, H//2 + 200, size=18, color=TEXT_COLOR, centered=True)
        pygame.draw.rect(s, BUTTON_COLOR, self.start_button, border_radius=8)
        draw_text(s, "Start Game", self.start_button.x + 12, self.start_button.y + 8, size=24, color=WHITE)
        
        
    def draw_game_over_screen(self):
        s = self.screen
        s.fill(BG_COLOR)
        draw_text(s, "Quantum Catan", W//2, H//4, size=48, color=TEXT_COLOR, centered=True)
        winner = max(self.players, key=lambda p: p.score)
        draw_text(s, f"Game Over! Winner: {winner.name} (Score: {winner.score})", W//2, H//2 - 40, size=24, color=TEXT_COLOR, centered=True)
        draw_text(s, "Final Scores:", W//2, H//2 + 10, size=20, color=TEXT_COLOR, centered=True)
        for i, p in enumerate(sorted(self.players, key=lambda p: p.score, reverse=True)):
            draw_text(s, f"{p.name}: {p.score}", W//2, H//2 + 50 + i*30, size=18, color=TEXT_COLOR, centered=True) 
        pygame.draw.rect(s, BUTTON_COLOR, self.restart_button, border_radius=8)
        draw_text(s, "Restart Game", self.restart_button.x + 12, self.restart_button.y + 8, size=24, color=WHITE)
        
    def end_turn(self):
        
        self.trading = False
        self.trading_partner = None
        self.possible_trading_partners = []
        self.trading_partners_rects = []
        self.possible_victims = []
        self.possible_victims_rects = []
        self.settlements_placed = 0
        self.roads_placed = 0
        self.push_message(f"{self.players[self.current_player].name} ended their turn.")
        if self.round == 0:
            if self.current_player == self.num_players -1:
                self.push_message("First round of placement complete. Starting second round.") 
                self.round += 1
            else:
                self.current_player += 1
                
        elif self.round == 1:
            if self.current_player == 0:
                self.push_message("Second round of placement complete. Starting second round.")
                self.round += 1
            else:
                self.current_player -= 1
        
        else:
            if self.current_player == self.num_players -1:
                self.push_message("Turn cycle complete. Starting new round.")
                self.current_player = 0
                self.round += 1
            else:
                self.current_player = (self.current_player + 1) % self.num_players

            
        
        if self.round >= 2:
            if self.devMode == False: self.allowed_actions.append("rolling")
            if self.devMode == False: self.allowed_actions.append("placeDevCard")
        else:
            if self.devMode == False: self.allowed_actions.append("building")
        if self.devMode == False: 
            for k in ("trading", "building", "endTurn"):
                if k in self.allowed_actions:
                    self.allowed_actions.remove(k)

        self.last_roll = None


    def reset_game(self):
        self.round = 0
        self.current_player = 0
        self.allowed_actions = ["building"]
        self.last_roll = None
        
        # initialize players
        self.players = [Player(i) for i in range(self.num_players)]
        for i,p in enumerate(self.players):
            p.color = PLAYER_COLORS[i]
            p.resources = {"lumber":0,"brick":0,"wool":0,"grain":0,"ore":0}
            p.tokens = []
        # geometry & tiles
        self.unused_ent_group_numbers = [i+1 for i in range(10)]
        self.tiles = randomize_tiles()
        # randomly select 3 entangled pairs
        
        
        
        
        self.sea_tiles = generate_sea_ring()
        self.moving_robber = False
        self.entangling = False
        self.entangling_pair = []
        
        
        self.settlements_placed = 0
        self.roads_placed = 0
        
        self.trading = False
        self.trading_partner = None  # player index or "bank/port"
        self.possible_trading_partners = []  # list of player indices
        self.trading_partners_rects = []  # list of rects for clicking
        
        self.victim = None  # player index to steal from
        self.possible_victims = []  # list of (player_idx, building_type) adjacent to robber tile
        self.possible_victims_rects = []  # list of rects for clicking
        
        self.placing = None  # whether in placement mode
        self.sel = None
        
        # message/notification log (text, expires_at_ms)
        self.message_log = []   # list of (text, expiry_timestamp_ms)
        self.message_max = 6    # max messages shown

        # build graph
        _, self.hex_vertex_indices = compute_centers_and_polys(self.origin)
        #print(self.hex_vertex_indices)
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
        self.robber_idx = None
        # UI rectangles (placeholders)
        self.reset_rect = pygame.Rect(20,20,120,40)
        self.dice_rect = pygame.Rect(20,70,120,40)
        self.end_turn_rect = pygame.Rect(20, H-66, 120, 40)

        self.trade_rect = pygame.Rect(W-220, 240, 80, 20)
        # shop rects are computed each draw
        self.shop_rects = []
        self.shop_rects = []
        
        self.inspecting = False
        
        self.devMode = False
        self.last_settlement_pos = None
        self.milliseconds_passed = 0
        self.milliseconds_passed_at_roll = 0
        self.activated_settlements = []
        self.activated_cities = []
        
        self.longest_road = None
        
        pygame.mixer.music.load("../music/Quantum_Catan.wav")
        pygame.mixer.music.play()
        pygame.mixer.music.set_volume(0.2)
        
        """
        self.bgImage = pygame.image.load("QuantumCatan/img/bg.jpg")
        self.bgImage = pygame.transform.smoothscale(self.bgImage, (W, H))
       
        
        self.board = pygame.image.load("QuantumCatan/img/bg.png").convert_alpha()
        self.board = pygame.transform.smoothscale(self.board, (370, 490))
        """
        for p in range(self.num_entangled_pairs):
            while len(self.entangling_pair) < 2:
                tile_idx = random.randint(0, len(self.tiles)-1)
                resource_list = [t[1].get("resource") for t in self.entangling_pair]
                tile = self.tiles[tile_idx]
                if not (tile in self.entangling_pair or tile.get("quantum", False) or tile.get("resource") == "desert" or tile.get("resource") in resource_list):
                    self.entangling_pair.append((tile_idx, tile))
            self.unused_ent_group_numbers.sort()
            self.entangle_pair_of_normal_tiles(self.entangling_pair, self.unused_ent_group_numbers.pop(0), start=True)
            self.entangling_pair = []   

    # simple update hook called from main loop
    def update(self, dt):
        self.start_button = pygame.Rect(self.screen.get_width()//2 - 90, self.screen.get_height()//2 + 250, 180, 40)
        self.restart_button = pygame.Rect(self.screen.get_width()//2 - 105, self.screen.get_height()//2 + 200, 210, 40)
        if self.runningGame:
            if "trading" not in self.allowed_actions and not self.devMode:
                self.trading = False
                self.trading_partner = None
                self.possible_trading_partners = []
                self.trading_partners_rects = []       
                
            if self.round < 2:
                if (self.roads_placed == 1) and (self.settlements_placed == 1):
                    if "endTurn" not in self.allowed_actions:
                        if self.devMode == False: self.allowed_actions.append("endTurn")
                        
            if self.possible_victims != []:
                for k in ("building", "endTurn", "trading"):
                    if k in self.allowed_actions:
                        self.allowed_actions.remove(k)
            
            for player in self.players:
                if player.score >= 10 and self.runningGame:
                    self.push_message(f"{player.name} has won the game with a score of {player.score}!")
                    self.playerWon = True
                    self.runningGame = False
                    self.allowed_actions = []
            self.milliseconds_passed = pygame.time.get_ticks()
                
        """
        dt: milliseconds since last frame.
        Currently a no-op placeholder. Extend this to:
         - advance animations
         - process token timers / measurements
         - handle background game logic
        """
        # Example: if you later add per-player token timers, process them here.
        return
