"""
ml_model.py — Local Random Forest Classifier
=============================================
Manages the scikit-learn Random Forest model lifecycle:
  - Load model from: models/attention_classifier.joblib
  - Run inference on the f0–f4 feature vector
  - Hot-swap the .joblib file after retraining (no app restart)

Model size: ~5MB on disk. CPU-only. Fully offline.
"""

# TODO: Task Sequence 3 — implement inference + hot-swap logic
