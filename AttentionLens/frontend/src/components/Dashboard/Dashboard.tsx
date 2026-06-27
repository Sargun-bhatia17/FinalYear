// src/components/Dashboard/Dashboard.tsx
// Main live-status panel. Delegates to RiskDial + StateTag.
import React from "react";
import { Monitor } from "lucide-react";
import { RiskDial } from "../RiskDial/RiskDial";
import { StateTag } from "../StateTag/StateTag";
import type { LiveStatus } from "../../types";

interface Props { status: LiveStatus | undefined; isLoading: boolean }

export const Dashboard: React.FC<Props> = ({ status, isLoading }) => {
  if (isLoading || !status) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 flex items-center justify-center h-44">
        <span className="text-sm text-gray-400 animate-pulse">Loading live status…</span>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Live Status</h2>
      <div className="flex items-center gap-6">
        <RiskDial score={status.risk_score} />
        <div className="flex-1 space-y-3">
          <StateTag state={status.current_state} />
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <Monitor size={14} className="text-gray-400" />
            <span className="font-medium truncate">{status.active_process}</span>
          </div>
          <p className="text-xs text-gray-400 truncate" title={status.active_window_title}>
            {status.active_window_title}
          </p>
          {status.fired_protocol && (
            <span className="text-xs bg-purple-50 text-purple-600 ring-1 ring-purple-200 px-2 py-0.5 rounded-full">
              {status.fired_protocol.replace(/_/g, " ")}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
