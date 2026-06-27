// src/api/client.ts
// Generic HTTP client. All fetch logic lives here — never in components.

import { invoke } from "@tauri-apps/api/core";

export class EngineOfflineError extends Error {
  constructor() { super("AttentionLens engine is offline"); this.name = "EngineOfflineError"; }
}

// Read port from data/port.json via Tauri IPC.
// Falls back to 8421 when running in browser dev mode (no Tauri).
async function resolvePort(): Promise<number | null> {
  try {
    const raw = await invoke<string>("read_port_file");
    const parsed = JSON.parse(raw);
    return typeof parsed === "number" ? parsed : null;
  } catch {
    return 8421; // browser dev fallback
  }
}

let _baseUrl: string | null = null;

async function baseUrl(): Promise<string> {
  if (_baseUrl) return _baseUrl;
  const port = await resolvePort();
  if (!port) throw new EngineOfflineError();
  _baseUrl = `http://127.0.0.1:${port}`;
  return _baseUrl;
}

export async function get<T>(path: string): Promise<T> {
  const base = await baseUrl();
  const res = await fetch(`${base}${path}`);
  if (!res.ok) throw new EngineOfflineError();
  return res.json() as Promise<T>;
}
