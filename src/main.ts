import { createApp } from "vue";
import { getCurrentWindow } from "@tauri-apps/api/window";
import App from "./App.vue";
import "./styles.css";

async function bootstrap() {
  try {
    const win = getCurrentWindow();
    if (!(await win.isMaximized())) {
      await win.maximize();
    }
  } catch {
    // browser preview / unsupported
  }
  createApp(App).mount("#app");
}

void bootstrap();
