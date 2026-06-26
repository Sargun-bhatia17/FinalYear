import React from "react";
import { useAttentionSocket } from "./hooks/useAttentionSocket";
import { Dashboard } from "./components/Dashboard/Dashboard";
import { Timeline } from "./components/Timeline/Timeline";
import { AlertBanner } from "./components/AlertBanner/AlertBanner";
import { ModelStatus } from "./components/ModelStatus/ModelStatus";
import { Shield, Radio, Settings } from "lucide-react";
import "./App.css";

function App() {
  const { isConnected, state } = useAttentionSocket("ws://localhost:8421");

  return (
    <div className="app-container">
      {/* Premium Navigation Header */}
      <header className="header-navbar glass-card">
        <div className="brand-section">
          <span className="brand-logo">🔍</span>
          <div className="brand-texts">
            <h1>AttentionLens</h1>
            <span className="brand-tagline">Local &amp; Privacy-First Cognitive Computing</span>
          </div>
        </div>

        <div className="header-actions">
          {/* Privacy badge */}
          <div className="privacy-badge">
            <Shield size={14} className="icon-green" />
            <span>100% Offline</span>
          </div>
          
          {/* Socket Connection status dot */}
          <div className={`connection-status ${isConnected ? "connected" : "disconnected"}`}>
            <Radio size={14} className="conn-icon" />
            <span>{isConnected ? "Engine Connected" : "Connecting to Engine..."}</span>
          </div>

          <button className="settings-button" title="Configure Taxonomy Settings">
            <Settings size={18} />
          </button>
        </div>
      </header>

      {/* Main layout container */}
      <main className="main-content">
        {/* Dynamic Alert Banner */}
        <AlertBanner state={state} />

        {/* Real-time score & process widget dashboard */}
        <Dashboard state={state} />

        {/* Two column grid layout for detailed panels */}
        <div className="panels-grid">
          <Timeline state={state} />
          <ModelStatus state={state} />
        </div>
      </main>

      <footer className="app-footer">
        <p>AttentionLens v1.0.0 · Local SQLite &amp; Random Forest personalization</p>
      </footer>
    </div>
  );
}

export default App;
