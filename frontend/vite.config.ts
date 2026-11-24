import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import {defineConfig} from "vite"

export default defineConfig({
    plugins: [react(), tailwindcss()],
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
    server: {
        host: '0.0.0.0', // Makes the server available on the network
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://localhost:8001',  // ← 8001 instead of 8000!
                changeOrigin: true,
            }
        }
    }
})
