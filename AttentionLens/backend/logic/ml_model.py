import os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

class AttentionClassifier:
    def __init__(self, model_path=None):
        if model_path is None:
            # Locate relative to the engine directory: engine/../models/attention_classifier.joblib
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            models_dir = os.path.join(base_dir, "models")
            os.makedirs(models_dir, exist_ok=True)
            self.model_path = os.path.join(models_dir, "attention_classifier.joblib")
        else:
            self.model_path = model_path
            
        self.model = None
        self.classes_ = ["Deep Work", "Pondering", "Passive Leisure", "Idle_Away"]
        self.load_or_create_model()

    def load_or_create_model(self):
        """Loads model from disk, or initializes and fits a default fallback model."""
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
                return
            except Exception as e:
                print(f"Error loading model: {e}. Recreating fallback.")
                
        # Initialize fallback model trained on a small dummy dataset
        self.model = RandomForestClassifier(n_estimators=10, max_depth=3, random_state=42)
        
        # Dummy data: [f0 (density), f1 (scroll), f2 (entropy), f3 (core ratio), f4 (time of day)]
        # Target classes: 0: "Deep Work", 1: "Pondering", 2: "Passive Leisure", 3: "Idle_Away"
        X_dummy = np.array([
            [50.0, 0.0, 0.0, 1.0, 10.0],  # high input, zero scroll, zero entropy, core app -> Deep Work
            [20.0, 2.0, 0.5, 0.9, 14.0],  # moderate input, core app -> Deep Work
            [1.0, 1.0, 0.0, 1.0, 11.0],   # low input, low scroll, core app -> Pondering
            [2.0, 50.0, 0.2, 0.0, 15.0],  # low input, high scroll, leisure -> Passive Leisure
            [0.0, 0.0, 0.0, 0.0, 16.0],   # zero inputs -> Idle_Away
            [0.0, 0.0, 0.8, 0.5, 20.0],   # zero inputs, high entropy -> Idle_Away
        ])
        y_dummy = np.array([0, 0, 1, 2, 3, 3])
        
        self.model.fit(X_dummy, y_dummy)
        self.save_model()

    def save_model(self):
        joblib.dump(self.model, self.model_path)

    def predict(self, feature_vector: np.ndarray) -> Tuple[str, float]:
        """
        Predicts state and calculates risk score based on probability.
        Returns:
            Tuple[str, float]: (predicted_state_name, attention_risk_score)
        """
        # Ensure correct shape
        x = feature_vector.reshape(1, -1)
        
        # Predict probability
        probs = self.model.predict_proba(x)[0]
        pred_idx = np.argmax(probs)
        predicted_class_id = self.model.classes_[pred_idx]
        
        # Map class ID back to class name
        # If fallback model classes are indices, map to names
        if isinstance(predicted_class_id, (int, np.integer)):
            predicted_state = self.classes_[predicted_class_id]
        else:
            predicted_state = str(predicted_class_id)
            
        # Attention Risk Score calculation based on probabilities of non-productive states
        # Risk is high if probability of Passive Leisure is high, or if we have high entropy
        # Let's say risk = prob(Leisure) + 0.5 * prob(Idle)
        # We index based on class structure
        class_mapping = {c: i for i, c in enumerate(self.model.classes_)}
        
        leisure_idx = class_mapping.get(2, class_mapping.get("Passive Leisure", -1))
        idle_idx = class_mapping.get(3, class_mapping.get("Idle_Away", -1))
        
        p_leisure = probs[leisure_idx] if leisure_idx != -1 else 0.0
        p_idle = probs[idle_idx] if idle_idx != -1 else 0.0
        
        # Risk score bounds between 0.0 and 1.0
        risk_score = float(np.clip(p_leisure * 1.0 + p_idle * 0.5, 0.0, 1.0))
        
        return predicted_state, risk_score

    def retrain(self, X_train: np.ndarray, y_train: np.ndarray):
        """Retrains the Random Forest model and saves it to disk."""
        # Ensure we map class names to class indices/categories if they are strings
        y_mapped = []
        for label in y_train:
            if isinstance(label, str):
                if label == "Deep Work":
                    y_mapped.append(0)
                elif label == "Pondering":
                    y_mapped.append(1)
                elif label == "Passive Leisure":
                    y_mapped.append(2)
                else:
                    y_mapped.append(3)
            else:
                y_mapped.append(int(label))
                
        # Fit new classifier
        new_model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
        new_model.fit(X_train, np.array(y_mapped))
        
        self.model = new_model
        self.save_model()
