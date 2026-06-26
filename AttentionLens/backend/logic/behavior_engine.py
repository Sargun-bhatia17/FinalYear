import math
from typing import List, Dict, Tuple

class BehaviorEngine:
    def __init__(self):
        # Distance matrix representing Category Distance (C_D)
        # Structure: (from_category, to_category) -> score
        self.category_distance_map = {
            ("Core_Tool", "Core_Tool"): 0.0,
            ("Core_Tool", "Supporting_Tool"): 0.1,
            ("Core_Tool", "Leisure"): 1.0,
            
            ("Supporting_Tool", "Core_Tool"): 0.0,
            ("Supporting_Tool", "Supporting_Tool"): 0.0,
            ("Supporting_Tool", "Leisure"): 0.8,
            
            ("Leisure", "Core_Tool"): 0.2,
            ("Leisure", "Supporting_Tool"): 0.2,
            ("Leisure", "Leisure"): 0.0
        }

    def calculate_interaction_density(self, keystrokes: int, clicks: int) -> int:
        """
        I_D = keystroke_count + mouse_click_count
        """
        return keystrokes + clicks

    def calculate_scroll_velocity(self, scroll_delta_y: int, duration_seconds: float = 60.0) -> float:
        """
        S_V = abs(scroll_delta_y) / duration_seconds
        """
        if duration_seconds <= 0:
            return 0.0
        return abs(scroll_delta_y) / duration_seconds

    def calculate_context_switching_entropy(self, app_categories: List[str]) -> float:
        """
        E_C = -sum(p_i * log2(p_i)) over rolling window
        """
        if not app_categories:
            return 0.0
            
        counts = {}
        for cat in app_categories:
            counts[cat] = counts.get(cat, 0) + 1
            
        entropy = 0.0
        total = len(app_categories)
        for cat, count in counts.items():
            p_i = count / total
            entropy -= p_i * math.log2(p_i)
            
        return entropy

    def calculate_category_distance(self, from_cat: str, to_cat: str) -> float:
        """
        C_D score for a transition from one app category to another.
        """
        return self.category_distance_map.get((from_cat, to_cat), 0.5)
