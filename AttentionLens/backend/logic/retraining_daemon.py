import time
import threading
import datetime
import numpy as np
from typing import Optional

class RetrainingDaemon(threading.Thread):
    def __init__(self, repository, classifier, check_interval_seconds=60):
        super().__init__()
        self.repository = repository
        self.classifier = classifier
        self.check_interval_seconds = check_interval_seconds
        self.daemon = True
        self.running = False
        self.last_trained_count = 0
        self.last_trained_time = datetime.datetime.now()

    def run(self):
        self.running = True
        # Set initial count
        try:
            self.last_trained_count = self.repository.get_session_count()
        except Exception:
            self.last_trained_count = 0
            
        while self.running:
            try:
                self.check_and_retrain()
            except Exception as e:
                print(f"Error in RetrainingDaemon loop: {e}")
            time.sleep(self.check_interval_seconds)

    def stop(self):
        self.running = False

    def check_and_retrain(self):
        current_count = self.repository.get_session_count()
        current_time = datetime.datetime.now()
        
        # Condition: 100 new rows or 7 days elapsed
        days_elapsed = (current_time - self.last_trained_time).days
        rows_added = current_count - self.last_trained_count
        
        if rows_added >= 100 or days_elapsed >= 7:
            print(f"Retraining triggered: {rows_added} new rows, {days_elapsed} days elapsed.")
            self.perform_retraining()
            self.last_trained_count = current_count
            self.last_trained_time = current_time

    def perform_retraining(self):
        """Extracts sessions, builds feature matrix, and retrains classifier."""
        # Retrieve sessions
        sessions = self.repository.get_all_sessions(limit=1000)
        if len(sessions) < 10:
            print("Not enough data to retrain (minimum 10 sessions required).")
            return
            
        X = []
        y = []
        
        for sess in sessions:
            # sess fields: id, start_time, end_time, primary_process, primary_category, 
            #              scroll_velocity, input_density, has_text_selection, calculated_state, attention_risk_score
            scroll_vel = sess[5]
            input_dens = sess[6]
            category = sess[4]
            state = sess[8]
            
            # Reconstruct basic features (f0-f4) for training from DB
            f0 = float(input_dens)
            f1 = float(scroll_vel)
            # Let's estimate details from session row if direct vectors aren't stored
            f2 = 0.5 if category == "Supporting_Tool" else (0.0 if category == "Core_Tool" else 1.0)
            f3 = 1.0 if category == "Core_Tool" else 0.0
            
            # Format time-of-day float
            try:
                dt = datetime.datetime.strptime(sess[1], "%Y-%m-%d %H:%M:%S")
                f4 = dt.hour + (dt.minute / 60.0)
            except Exception:
                f4 = 12.0
                
            X.append([f0, f1, f2, f3, f4])
            y.append(state)
            
        X_train = np.array(X, dtype=np.float32)
        y_train = np.array(y)
        
        # Fit model and hot-swap
        try:
            self.classifier.retrain(X_train, y_train)
            print("Classifier retrained and hot-swapped successfully.")
        except Exception as e:
            print(f"Failed to retrain model: {e}")
            
    def force_retrain(self):
        """Forces manual retraining on the background thread."""
        threading.Thread(target=self.perform_retraining, daemon=True).start()
