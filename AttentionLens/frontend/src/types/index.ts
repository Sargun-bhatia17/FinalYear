// src/types/index.ts
// Single source of truth for all TypeScript interfaces.

export interface LiveStatus {
  timestamp: string;
  active_process: string;
  active_window_title: string;
  current_state: string;
  risk_score: number;
  fired_protocol: string | null;
  data_quality: string;
}

export interface SessionBlock {
  start_time: string;
  end_time: string;
  state: string;
  risk_score: number;
  primary_process: string;
}

export interface DailySummary {
  date: string;
  sessions: SessionBlock[];
  deep_work_minutes: number;
  idle_minutes: number;
  model_session_count: number;
  model_last_trained: string | null;
}

export interface HealthStatus {
  status: string;
  port: number;
}

export interface AlertInfo {
  actionable_prompt: string;
  suggested_action: string;
}

// Prop shapes
export interface RiskDialProps { score: number }
export interface StateTagProps { state: string }
export interface AlertBannerProps { risk: number; alert: AlertInfo | null; sinceMs: number }
export interface TimelineProps { sessions: SessionBlock[] }
export interface ModelStatusProps { health: HealthStatus | undefined; summary: DailySummary | undefined }
