import { useState, useEffect, useCallback, useRef } from "react";

export interface AttentionState {
  attention_score: number;
  calculated_state: string;
  active_process: string;
  active_title: string;
  active_category: string;
  ml_model_status: string;
  session_count: number;
  recent_sessions: Array<[
    number,      // id
    string,      // start_time
    string,      // end_time
    string,      // primary_process
    string,      // primary_category
    number,      // scroll_velocity
    number,      // input_density
    boolean,     // has_text_selection
    string,      // calculated_state
    number       // attention_risk_score
  ]>;
  current_alert: {
    alert_trigger: string;
    primary_cause: string;
    actionable_prompt: string;
    suggested_action: string;
  } | null;
}

const DEFAULT_STATE: AttentionState = {
  attention_score: 0.0,
  calculated_state: "Deep Work",
  active_process: "Initializing...",
  active_title: "Connecting to sidecar process...",
  active_category: "Core_Tool",
  ml_model_status: "Cold Start",
  session_count: 0,
  recent_sessions: [],
  current_alert: null
};

export function useAttentionSocket(url: string = "ws://localhost:8421") {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [state, setState] = useState<AttentionState>(DEFAULT_STATE);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.close();
    }

    const ws = new WebSocket(url);
    socketRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected to AttentionLens Sidecar Engine.");
      setIsConnected(true);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "state_update") {
          setState((prev) => ({
            ...prev,
            ...payload.data
          }));
        } else if (payload.type === "attention_alert") {
          setState((prev) => ({
            ...prev,
            current_alert: payload.data
          }));
        }
      } catch (err) {
        console.error("Failed to parse WebSocket message:", err);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      console.log("WebSocket connection closed. Attempting reconnect in 3s...");
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      ws.close();
    };
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  const sendAction = useCallback((action: string, payload: unknown) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ action, payload }));
    }
  }, []);

  return { isConnected, state, sendAction };
}
