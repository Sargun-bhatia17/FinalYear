// src/hooks/useAttentionSocket.ts
// Legacy hook kept for backward compatibility — now wraps useLiveStatus.
// No WebSocket logic; polling is done via TanStack Query in src/api/hooks.ts.
export { useLiveStatus as useAttentionSocket } from "../api/hooks";
