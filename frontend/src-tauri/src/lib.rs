use tauri::WebviewWindow;

/// 切换窗口 click-through（穿透点击到后方应用）
#[tauri::command]
fn set_click_through(window: WebviewWindow, enabled: bool) {
    let _ = window.set_ignore_cursor_events(enabled);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![set_click_through])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
