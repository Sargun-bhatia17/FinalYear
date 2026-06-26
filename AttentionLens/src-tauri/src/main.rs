#![cfg_attr(
  all(not(debug_assertions), target_os = "windows"),
  windows_subsystem = "windows"
)]

use tauri::api::process::Command;

fn main() {
  tauri::Builder::default()
    .setup(|app| {
      // Spawns the engine sidecar process.
      // In production, Tauri bundles the engine binary.
      // In development, the sidecar can be configured or mocked.
      match Command::new_sidecar("engine") {
        Ok(cmd) => {
          match cmd.spawn() {
            Ok((mut rx, _child)) => {
              tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                  if let tauri::api::process::CommandEvent::Stdout(line) = event {
                    println!("[Sidecar stdout] {}", line);
                  } else if let tauri::api::process::CommandEvent::Stderr(line) = event {
                    eprintln!("[Sidecar stderr] {}", line);
                  }
                }
              });
            }
            Err(e) => eprintln!("Failed to spawn engine sidecar process: {}", e),
          }
        }
        Err(e) => eprintln!("Failed to construct engine sidecar: {}", e),
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
