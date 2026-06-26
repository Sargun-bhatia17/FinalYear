import React from "react";
import { AttentionState } from "../../hooks/useAttentionSocket";
import { AlertOctagon, X } from "lucide-react";
import "./AlertBanner.css";

interface AlertBannerProps {
  state: AttentionState;
}

export const AlertBanner: React.FC<AlertBannerProps> = ({ state }) => {
  const alert = state.current_alert;
  
  if (!alert) return null;

  return (
    <div className="alert-banner-container glass-card border-glow">
      <div className="alert-icon-wrapper">
        <AlertOctagon className="alert-icon animate-pulse" />
      </div>
      <div className="alert-content">
        <div className="alert-title-row">
          <h4>{alert.alert_trigger.replace(/_/g, " ")}</h4>
          <span className="badge">Action Required</span>
        </div>
        <p className="cause"><strong>Diagnosis:</strong> {alert.primary_cause}</p>
        <p className="prompt">{alert.actionable_prompt}</p>
        {alert.suggested_action && (
          <div className="actions-row">
            <button className="action-button">{alert.suggested_action}</button>
          </div>
        )}
      </div>
    </div>
  );
};
