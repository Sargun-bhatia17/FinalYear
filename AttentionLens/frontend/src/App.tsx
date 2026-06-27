// src/App.tsx
// Root component. Wires API hooks to components. No business logic here.
import { useRef } from "react";
import { Shield } from "lucide-react";
import { useLiveStatus, useDailySummary, useHealth } from "./api/hooks";
import { Dashboard } from "./components/Dashboard/Dashboard";
import { Timeline } from "./components/Timeline/Timeline";
import { AlertBanner } from "./components/AlertBanner/AlertBanner";
import { ModelStatus } from "./components/ModelStatus/ModelStatus";
import "./index.css";

export default function App() {
  const { data: status, isLoading, isError } = useLiveStatus();
  const { data: summary }  = useDailySummary();
  const { data: health }   = useHealth();

  // Track when risk first went above 0.75
  const highRiskSince = useRef<number | null>(null);
  const risk = status?.risk_score ?? 0;
  if (risk >= 0.75 && !highRiskSince.current) highRiskSince.current = Date.now();
  if (risk < 0.75)                            highRiskSince.current = null;
  const sinceMs = highRiskSince.current ? Date.now() - highRiskSince.current : 0;

  if (isError) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center space-y-2">
          <p className="text-2xl">⏳</p>
          <p className="text-sm font-medium text-gray-500">Engine Starting…</p>
          <p className="text-xs text-gray-400">Waiting for AttentionLens sidecar</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f5f5f7] text-gray-900">
      {/* Header */}
      <header className="sticky top-0 bg-white/80 backdrop-blur-md border-b border-gray-100 z-10">
        <div className="max-w-4xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">🔍</span>
            <span className="font-semibold text-gray-800 text-sm">AttentionLens</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-500">
            <Shield size={12} className="text-teal-500" />
            <span>100% Offline</span>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-4xl mx-auto px-6 py-6 space-y-4">
        <AlertBanner risk={risk}
          alert={status ? { actionable_prompt: "High attention risk detected.",
            suggested_action: "Consider a short break or switching tasks." } : null}
          sinceMs={sinceMs} />

        <Dashboard status={status} isLoading={isLoading} />

        <Timeline sessions={summary?.sessions ?? []} />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <ModelStatus health={health} summary={summary} />
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Today</h2>
            <div className="grid grid-cols-2 gap-4">
              {[{ label: "Deep Work", value: `${summary?.deep_work_minutes ?? 0} min`, color: "text-teal-600" },
                { label: "Idle", value: `${summary?.idle_minutes ?? 0} min`, color: "text-gray-400" }]
                .map(({ label, value, color }) => (
                  <div key={label}>
                    <p className="text-xs text-gray-400 mb-1">{label}</p>
                    <p className={`text-2xl font-bold ${color}`}>{value}</p>
                  </div>
              ))}
            </div>
          </div>
        </div>
      </main>

      <footer className="max-w-4xl mx-auto px-6 py-4 text-center text-xs text-gray-400">
        AttentionLens v1.0.0 · Local SQLite &amp; Random Forest
      </footer>
    </div>
  );
}
