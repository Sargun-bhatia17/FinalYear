import React from "react";
import { AttentionState } from "../../hooks/useAttentionSocket";
import { Activity, MousePointer, HelpCircle, Laptop } from "lucide-react";
import "./Dashboard.css";

interface DashboardProps {
  state: AttentionState;
}

export const Dashboard: React.FC<DashboardProps> = ({ state }) => {
  const scorePercent = Math.round(state.attention_score * 100);
  
  // Calculate visual properties for SVG circle gauge
  const radius = 80;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (state.attention_score * circumference);
  
  // Determine color based on risk score
  let scoreColor = "var(--color-deep-work)";
  if (state.attention_score > 0.75) {
    scoreColor = "var(--color-leisure)";
  } else if (state.attention_score > 0.4) {
    scoreColor = "var(--color-pondering)";
  }

  // Get state badge styling
  const getStateBadgeClass = (s: string) => {
    switch (s) {
      case "Deep Work": return "state-badge deep-work";
      case "Pondering": return "state-badge pondering";
      case "Passive Leisure": return "state-badge leisure";
      default: return "state-badge idle";
    }
  };

  return (
    <div className="dashboard-grid">
      {/* 1. Real-time Risk Score Gauge */}
      <div className="glass-card gauge-container">
        <h3>Attention Risk Score</h3>
        <div className="gauge-wrapper">
          <svg className="gauge-svg" width="200" height="200" viewBox="0 0 200 200">
            <circle
              className="gauge-bg"
              cx="100"
              cy="100"
              r={radius}
              stroke="rgba(255,255,255,0.03)"
              strokeWidth="14"
              fill="transparent"
            />
            <circle
              className="gauge-progress"
              cx="100"
              cy="100"
              r={radius}
              stroke={scoreColor}
              strokeWidth="14"
              fill="transparent"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              style={{ transition: "stroke-dashoffset 0.8s ease-in-out, stroke 0.3s ease" }}
            />
          </svg>
          <div className="gauge-content">
            <span className="gauge-value">{scorePercent}%</span>
            <span className="gauge-label">RISK LEVEL</span>
          </div>
        </div>
        <div className="gauge-footer">
          <span>Active State: </span>
          <span className={getStateBadgeClass(state.calculated_state)}>
            {state.calculated_state}
          </span>
        </div>
      </div>

      {/* 2. Active Session Telemetry Details */}
      <div className="glass-card telemetry-container">
        <h3>Current Window Context</h3>
        <div className="process-details">
          <div className="process-header">
            <Laptop className="process-icon" />
            <div>
              <div className="process-name">{state.active_process}</div>
              <div className="process-category">{state.active_category.replace("_", " ")}</div>
            </div>
          </div>
          <div className="window-title-box">
            <span className="label">Title:</span>
            <span className="value" title={state.active_title}>{state.active_title}</span>
          </div>
        </div>

        <div className="metrics-grid">
          {/* Simulated stats calculated from recent aggregates for display */}
          <div className="metric-item">
            <div className="metric-header">
              <MousePointer size={16} />
              <span>Input Density</span>
            </div>
            <div className="metric-value">
              {state.recent_sessions.length > 0 ? state.recent_sessions[0][6] : 0} <span className="unit">events/m</span>
            </div>
          </div>

          <div className="metric-item">
            <div className="metric-header">
              <Activity size={16} />
              <span>Scroll Velocity</span>
            </div>
            <div className="metric-value">
              {state.recent_sessions.length > 0 ? Math.round(state.recent_sessions[0][5]) : 0} <span className="unit">px/s</span>
            </div>
          </div>

          <div className="metric-item">
            <div className="metric-header">
              <HelpCircle size={16} />
              <span>Selection Flag</span>
            </div>
            <div className="metric-value">
              {state.recent_sessions.length > 0 && state.recent_sessions[0][7] ? "Active" : "Inactive"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
