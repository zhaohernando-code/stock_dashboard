import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-antd": ["antd", "@ant-design/icons"],
          "vendor-echarts": ["echarts"],
          "vendor-react": ["react", "react-dom"],
        },
      },
    },
  },
});
