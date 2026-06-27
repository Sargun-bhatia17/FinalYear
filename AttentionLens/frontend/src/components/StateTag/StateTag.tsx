// src/components/StateTag/StateTag.tsx
// Coloured badge for the current attention state.
import React from "react";
import type { StateTagProps } from "../../types";

const STATE_STYLES: Record<string, string> = {
  Deep_Work:       "bg-teal-50 text-teal-700 ring-1 ring-teal-200",
  Pondering:       "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
  Passive_Leisure: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  Active_Meeting:  "bg-purple-50 text-purple-700 ring-1 ring-purple-200",
  Idle_Away:       "bg-gray-100 text-gray-500 ring-1 ring-gray-200",
  Unknown:         "bg-gray-100 text-gray-400 ring-1 ring-gray-200",
};

const STATE_LABELS: Record<string, string> = {
  Deep_Work:       "Deep Work",
  Pondering:       "Pondering",
  Passive_Leisure: "Passive Leisure",
  Active_Meeting:  "Active Meeting",
  Idle_Away:       "Idle / Away",
  Unknown:         "Unknown",
};

export const StateTag: React.FC<StateTagProps> = ({ state }) => {
  const cls   = STATE_STYLES[state] ?? STATE_STYLES["Unknown"];
  const label = STATE_LABELS[state] ?? state.replace(/_/g, " ");
  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${cls}`}>
      {label}
    </span>
  );
};
