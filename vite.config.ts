import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ base: '/casa/', plugins: [react()], build: { chunkSizeWarningLimit: 1100 }, server: { port: 5177, proxy: { '/casa/api': 'http://127.0.0.1:8765', '/casa/auth': 'http://127.0.0.1:8765' } } });
