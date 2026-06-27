// src/api/hooks.ts
// All TanStack Query hooks. No data fetching outside this file.

import { useQuery } from "@tanstack/react-query";
import { get } from "./client";
import type { LiveStatus, DailySummary, HealthStatus } from "../types";

export function useLiveStatus() {
  return useQuery<LiveStatus>({
    queryKey: ["live-status"],
    queryFn: () => get<LiveStatus>("/live-status"),
    refetchInterval: 5_000,
    retry: false,
  });
}

export function useDailySummary() {
  return useQuery<DailySummary>({
    queryKey: ["daily-summary"],
    queryFn: () => get<DailySummary>("/daily-summary"),
    refetchInterval: 60_000,
    retry: false,
  });
}

export function useHealth() {
  return useQuery<HealthStatus>({
    queryKey: ["health"],
    queryFn: () => get<HealthStatus>("/health"),
    refetchInterval: 30_000,
    retry: false,
  });
}
