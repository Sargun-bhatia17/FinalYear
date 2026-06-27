// src/components/RiskDial/RiskDial.tsx
// SVG semi-circle arc dial. Score 0–1 maps to 0–180°.
// Colors: teal (<0.4), amber (0.4–0.74), red (>=0.75).
import React from "react";
import type { RiskDialProps } from "../../types";

function dialColor(score: number): string {
  if (score >= 0.75) return "#FF6347";
  if (score >= 0.40) return "#FFBF00";
  return "#008080";
}

export const RiskDial: React.FC<RiskDialProps> = ({ score }) => {
  const clamped  = Math.max(0, Math.min(1, score));
  const angleDeg = clamped * 180;
  const R = 70;
  const cx = 90; const cy = 90;

  // Arc end point from –180° (left) sweeping clockwise to 0° (right)
  const startRad = Math.PI;
  const endRad   = Math.PI - (angleDeg * Math.PI) / 180;
  const x1 = cx + R * Math.cos(startRad);
  const y1 = cy + R * Math.sin(startRad);
  const x2 = cx + R * Math.cos(endRad);
  const y2 = cy + R * Math.sin(endRad);
  const largeArc = angleDeg > 180 ? 1 : 0;
  const color = dialColor(clamped);

  return (
    <svg width="180" height="100" viewBox="0 0 180 100" aria-label={`Risk ${Math.round(clamped * 100)}%`}>
      {/* Track */}
      <path d={`M ${cx - R} ${cy} A ${R} ${R} 0 0 1 ${cx + R} ${cy}`}
        fill="none" stroke="#e5e5ea" strokeWidth="12" strokeLinecap="round" />
      {/* Fill */}
      {angleDeg > 0 && (
        <path d={`M ${x1} ${y1} A ${R} ${R} 0 ${largeArc} 1 ${x2} ${y2}`}
          fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
          style={{ transition: "all 0.7s ease" }} />
      )}
      {/* Label */}
      <text x={cx} y={cy - 6} textAnchor="middle"
        fontSize="22" fontWeight="700" fill={color} style={{ transition: "fill 0.3s" }}>
        {Math.round(clamped * 100)}%
      </text>
      <text x={cx} y={cy + 10} textAnchor="middle" fontSize="9" fill="#8e8e93" letterSpacing="1">
        RISK SCORE
      </text>
    </svg>
  );
};
