import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const PORT = 8000
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/agui": {
        target: `http://127.0.0.1:${PORT}`,
        changeOrigin: true,
      },
      "/status": {
        target: `http://127.0.0.1:${PORT}`,
        changeOrigin: true,
      },
    },
  },
});
