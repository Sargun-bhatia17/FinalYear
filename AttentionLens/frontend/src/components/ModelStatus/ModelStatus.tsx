// src/components/ModelStatus/ModelStatus.tsx
// Polls /health every 30s. Displays training badge + session count.
import React from "react";
import { BrainCircuit } from "lucide-react";
import type { ModelStatusProps } from "../../types";

function fmtDate(iso: string | null): string {
  if (!iso) return "Never";
  try { return new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }); }
  catch { return iso; }
}

export const ModelStatus: React.FC<ModelStatusProps> = ({ health, summary }) => {
  const online   = health?.status === "ok";
  const trained  = summary?.model_last_trained ?? null;
  const sessions = summary?.model_session_count ?? 0;
  const N        = sessions;
  const w_ml     = Math.round(Math.min(0.8, N / 500) * 100);
  const w_rule   = 100 - w_ml;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <div className="flex items-center gap-2 mb-4">
        <BrainCircuit size={14} className="text-gray-400" />
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Model Status</h2>
        <span className={`ml-auto text-[10px] font-semibold px-2 py-0.5 rounded-full
          ${online ? "bg-teal-50 text-teal-700 ring-1 ring-teal-200" : "bg-gray-100 text-gray-400"}`}>
          {online ? "Online" : "Offline"}
        </span>
      </div>

      <p className="text-xs text-gray-500 mb-4">
        Trained {fmtDate(trained)} · <span className="font-semibold text-gray-700">{sessions}</span> sessions
      </p>

      {[{ label: "Rule Engine (W_rule)", pct: w_rule, color: "bg-blue-400" },
        { label: "ML Classifier (W_ml)",  pct: w_ml,   color: "bg-teal-400" }].map(({ label, pct, color }) => (
        <div key={label} className="mb-3">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{label}</span><span className="font-semibold">{pct}%</span>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${color} transition-all duration-700`}
              style={{ width: `${pct}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
};
