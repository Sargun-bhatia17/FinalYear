import datetime
from typing import List, Dict, Any, Tuple
import numpy as np

class FeatureEngineer:
    def __init__(self, repository):
        self.repository = repository

    def get_time_of_day_index(self, dt: datetime.datetime = None) -> float:
        """
        Calculates time-of-day float index (e.g., 14.5 = 2:30 PM)
        """
        if dt is None:
            dt = datetime.datetime.now()
        return dt.hour + (dt.minute / 60.0) + (dt.second / 3600.0)

    def build_feature_vector(self, 
                             current_input_density: int, 
                             current_scroll_velocity: float, 
                             current_entropy: float,
                             current_category: str) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Builds a 5-dimensional feature vector f0-f4.
        Returns:
            Tuple[np.ndarray, dict]: (5D numpy array, dictionary of raw values)
        """
        # Fetch the last 5 sessions (approx. 5 minutes of data) to calculate averages
        recent_sessions = self.repository.get_all_sessions(limit=5)
        
        # Include current window's prospective data
        all_densities = [current_input_density]
        all_scrolls = [current_scroll_velocity]
        categories_count = 1 if current_category == "Core_Tool" else 0
        total_count = 1
        
        for sess in recent_sessions:
            # sess fields: id, start_time, end_time, primary_process, primary_category, scroll_velocity, input_density, has_text_selection, calculated_state, attention_risk_score
            all_densities.append(sess[6])
            all_scrolls.append(sess[5])
            if sess[4] == "Core_Tool":
                categories_count += 1
            total_count += 1
            
        f0 = float(np.mean(all_densities))
        f1 = float(np.mean(all_scrolls))
        f2 = current_entropy
        f3 = float(categories_count / total_count)
        f4 = self.get_time_of_day_index()
        
        vector = np.array([f0, f1, f2, f3, f4], dtype=np.float32)
        raw_dict = {
            "mean_interaction_density": f0,
            "mean_scroll_velocity": f1,
            "context_entropy": f2,
            "core_tool_ratio": f3,
            "time_of_day_index": f4
        }
        return vector, raw_dict
