// main.rs — Tauri Application Entry Point
// Responsibilities:
//   - Initialize the native desktop window
//   - Spawn the Python sidecar process (engine/main.py)
//   - Pass the randomized IPC port to the frontend via Tauri state

// TODO: Task Sequence 4 — implement sidecar spawning + IPC port handoff
fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running AttentionLens");
}
