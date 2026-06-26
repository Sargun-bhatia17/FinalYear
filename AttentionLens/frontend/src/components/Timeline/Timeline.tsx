import React from "react";
import { AttentionState } from "../../hooks/useAttentionSocket";
import { Clock, Terminal, ChevronRight } from "lucide-react";
import "./Timeline.css";

interface TimelineProps {
  state: AttentionState;
}

export const Timeline: React.FC<TimelineProps> = ({ state }) => {
  const getTimelineDotColor = (s: string) => {
    switch (s) {
      case "Deep Work": return "var(--color-deep-work)";
      case "Pondering": return "var(--color-pondering)";
      case "Passive Leisure": return "var(--color-leisure)";
      default: return "var(--color-idle)";
    }
  };

  const formatTime = (timeStr: string) => {
    try {
      const parts = timeStr.split(" ");
      if (parts.length > 1) {
        return parts[1]; // Returns HH:MM:SS
      }
      return timeStr;
    } catch {
      return timeStr;
    }
  };

  return (
    <div className="glass-card timeline-card">
      <div className="timeline-header">
        <div className="title-section">
          <Clock className="header-icon" />
          <h3>Session Timeline</h3>
        </div>
        <span className="count-label">{state.session_count} total sessions</span>
      </div>

      <div className="timeline-list-container">
        {state.recent_sessions.length === 0 ? (
          <div className="empty-timeline">
            <Terminal size={32} />
            <p>Waiting for minute aggregates to compile...</p>
          </div>
        ) : (
          <div className="timeline-list">
            {state.recent_sessions.map((sess) => {
              const [
                id,
                start_time,
                , // end_time
                primary_process,
                primary_category,
                scroll_velocity,
                input_density,
                , // has_text_selection
                calculated_state,
                attention_risk_score
              ] = sess;

              return (
                <div className="timeline-item" key={id}>
                  <div className="timeline-left">
                    <span className="timestamp">{formatTime(start_time)}</span>
                    <div 
                      className="timeline-dot" 
                      style={{ 
                        backgroundColor: getTimelineDotColor(calculated_state),
                        boxShadow: `0 0 10px ${getTimelineDotColor(calculated_state)}`
                      }}
                    />
                  </div>
                  <div className="timeline-body">
                    <div className="timeline-row">
                      <div className="process-info">
                        <span className="process-tag">{primary_process}</span>
                        <ChevronRight size={12} className="separator" />
                        <span className="category-tag">{primary_category.replace("_", " ")}</span>
                      </div>
                      <span className="state-text" style={{ color: getTimelineDotColor(calculated_state) }}>
                        {calculated_state}
                      </span>
                    </div>
                    <div className="timeline-row details">
                      <span>Inputs: <strong>{input_density}</strong> · Scroll: <strong>{Math.round(scroll_velocity)} px/s</strong></span>
                      <span className="risk-pill">Risk: <strong>{Math.round(attention_risk_score * 100)}%</strong></span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
