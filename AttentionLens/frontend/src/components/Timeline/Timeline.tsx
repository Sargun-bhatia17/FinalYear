// src/components/Timeline/Timeline.tsx
// Horizontal bar chart. Each block width = (duration_min / 1440) * 100.
// Tooltip on hover: primary_process + start/end times.
import React, { useState } from "react";
import { Clock } from "lucide-react";
import type { TimelineProps, SessionBlock } from "../../types";

const STATE_COLORS: Record<string, string> = {
  Deep_Work:       "#008080",
  Pondering:       "#60a5fa",
  Passive_Leisure: "#FFBF00",
  Active_Meeting:  "#a78bfa",
  Idle_Away:       "#d1d5db",
  Unknown:         "#e5e7eb",
};

function durationMin(s: SessionBlock): number {
  const ms = new Date(s.end_time).getTime() - new Date(s.start_time).getTime();
  return Math.max(1, ms / 60_000);
}

function fmt(iso: string): string {
  return iso.split(" ")[1]?.slice(0, 5) ?? iso;
}

export const Timeline: React.FC<TimelineProps> = ({ sessions }) => {
  const [hovered, setHovered] = useState<SessionBlock | null>(null);

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <div className="flex items-center gap-2 mb-4">
        <Clock size={14} className="text-gray-400" />
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Today's Timeline</h2>
      </div>

      {sessions.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-6">No sessions recorded today.</p>
      ) : (
        <>
          <div className="flex h-8 rounded-lg overflow-hidden gap-px relative">
            {sessions.map((s, i) => {
              const w = Math.max(0.3, (durationMin(s) / 1440) * 100);
              return (
                <div key={i} style={{ width: `${w}%`, background: STATE_COLORS[s.state] ?? "#e5e7eb" }}
                  className="transition-opacity hover:opacity-80 cursor-pointer"
                  onMouseEnter={() => setHovered(s)} onMouseLeave={() => setHovered(null)} />
              );
            })}
          </div>
          {hovered && (
            <div className="mt-3 bg-gray-50 rounded-xl px-4 py-2 text-xs text-gray-600 flex gap-4">
              <span className="font-semibold">{hovered.primary_process}</span>
              <span>{fmt(hovered.start_time)} – {fmt(hovered.end_time)}</span>
              <span className="text-gray-400">{hovered.state.replace(/_/g, " ")}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
};
