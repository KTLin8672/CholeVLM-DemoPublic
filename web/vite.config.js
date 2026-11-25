import { defineConfig } from 'vite';

// Every server binds loopback. The dev server is for this machine only;
// the built page is shared through `python -m chole_demo share` (ngrok, behind a password).
const api = 'http://127.0.0.1:8781';

export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': api, '/media': api },
  },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true },
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 1000 }, // three.js is ~600 kB
});
