// src/components/AlertBanner/AlertBanner.tsx
// Conditionally rendered when risk > 0.75 for 3+ consecutive minutes.
import React from "react";
import { AlertTriangle } from "lucide-react";
import type { AlertBannerProps } from "../../types";

const THREE_MINUTES_MS = 3 * 60 * 1000;

export const AlertBanner: React.FC<AlertBannerProps> = ({ risk, alert, sinceMs }) => {
  const shouldShow = risk >= 0.75 && sinceMs >= THREE_MINUTES_MS;
  if (!shouldShow || !alert) return null;

  return (
    <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl p-4 mb-4
                    animate-pulse-subtle shadow-sm">
      <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={20} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-red-800 mb-1">{alert.actionable_prompt}</p>
        <p className="text-xs text-red-600">{alert.suggested_action}</p>
      </div>
    </div>
  );
};
