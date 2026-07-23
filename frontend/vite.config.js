import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    host: true,
    strictPort: true,
    port: 5173,
    // AUTHORIZE YOUR DOMAIN HERE
    allowedHosts: ["teleshop-et.ddns.net", "indexgebeya.cfd", "www.indexgebeya.cfd"], 
    watch: {
      usePolling: true,
    },
    hmr: false
  }
})