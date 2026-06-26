import React from "react";
import { AttentionState } from "../../hooks/useAttentionSocket";
import { BrainCircuit, Info } from "lucide-react";
import "./ModelStatus.css";

interface ModelStatusProps {
  state: AttentionState;
}

export const ModelStatus: React.FC<ModelStatusProps> = ({ state }) => {
  const N = state.session_count;
  
  // Calculate trust weights according to fusion formulas
  const w_ml = Math.min(0.8, N / 500);
  const w_rule = 1.0 - w_ml;
  
  const w_ml_percent = Math.round(w_ml * 100);
  const w_rule_percent = Math.round(w_rule * 100);
  
  // Determine model status phrase
  let modelStatusText = "Rule Engine Cold Start";
  if (N >= 500) {
    modelStatusText = "Fully Trained (ML Lead)";
  } else if (N >= 50) {
    modelStatusText = "Growing (Linear Build-up)";
  }

  // Calculate sessions progress towards retraining (100 rows trigger)
  const retrainProgress = N % 100;

  return (
    <div className="glass-card status-card">
      <div className="status-header">
        <BrainCircuit className="status-icon" />
        <h3>Local Random Forest Status</h3>
      </div>
      
      <div className="status-body">
        {/* Status label */}
        <div className="status-row label-value">
          <span className="label">Pipeline Mode:</span>
          <span className="value status-highlight">{modelStatusText}</span>
        </div>

        {/* Retraining count tracker */}
        <div className="retrain-progress-section">
          <div className="label-row">
            <span>Retraining Daemon Progress</span>
            <span>{retrainProgress} / 100 sessions</span>
          </div>
          <div className="progress-bar-bg">
            <div 
              className="progress-bar-fill ml-fill" 
              style={{ width: `${retrainProgress}%` }}
            />
          </div>
        </div>

        {/* Trust blending bars */}
        <div className="weights-section">
          <h4>Fusion Weight Blending</h4>
          
          <div className="weight-item">
            <div className="label-row font-xs">
              <span>Rule Engine Weight (W_rule)</span>
              <span>{w_rule_percent}%</span>
            </div>
            <div className="progress-bar-bg">
              <div 
                className="progress-bar-fill rule-fill" 
                style={{ width: `${w_rule_percent}%` }}
              />
            </div>
          </div>

          <div className="weight-item">
            <div className="label-row font-xs">
              <span>ML Classifier Weight (W_ml)</span>
              <span>{w_ml_percent}%</span>
            </div>
            <div className="progress-bar-bg">
              <div 
                className="progress-bar-fill ml-fill" 
                style={{ width: `${w_ml_percent}%` }}
              />
            </div>
          </div>
        </div>

        <div className="info-box">
          <Info size={14} className="info-icon" />
          <p>
            The 20% Rule Floor is permanent. Key overrides (DSA Exception, Comic Loophole) will always be respected regardless of ML model confidence.
          </p>
        </div>
      </div>
    </div>
  );
};
