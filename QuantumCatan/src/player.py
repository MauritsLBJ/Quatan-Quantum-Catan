# src/player.py
# Player data structure and helpers
from .rendering import draw_text
class Player:
    def __init__(self, idx):
        self.idx = idx
        self.name = f"Player {idx+1}"
        self.color = None  # set by game_state
        # classical resources
        self.resources = {"lumber":0,"brick":0,"wool":0,"grain":0,"ore":0}
        # quantum tokens (list of token dicts from quantum.py)
        self.tokens = []
        # owned buildings tracked in game_state dictionaries (roads_owner / settlements_owner)
        # convenience: track score (number of settlements*1 + cities*2)
        self.score = 0
        self.held_dev_cards = {"knight": 0, "point": 0, "interference": 0}
        self.played_dev_cards = {"knight": 0, "point": 0, "interference": 0}
        self.buildables_placed = {"settlements":[], "cities":[], "roads":[]}
        self.knightmight = 0
        self.has_greatest_knightmight = False
        self.longest_road_roads = []

    def add_resource(self, resource, screen, amount=1, ):
        if resource in self.resources:
            self.resources[resource] += amount
            return f"{self.name} received {amount} {resource}(s). Now has {self.resources[resource]}."
        else:
            return f"{self.name} attempted to receive unknown resource '{resource}'."

    def can_afford(self, cost):
        for k,v in cost.items():
            if self.resources.get(k,0) < v:
                return False
        return True

    def pay_cost(self, cost):
        for k,v in cost.items():
            self.resources[k] -= v
