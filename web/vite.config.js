import { defineConfig } from 'vite';

// Every server binds loopback. The dev server is for this machine only;
// the built page is shared through `python -m chole_demo share` (ngrok, behind a password).
const api = 'http://127.0.0.1:8781';

// The built page carries no HTML comment: they are notes for whoever edits index.html,
// and a visitor's view-source is no place for them (2026-11-24).
const stripHtmlComments = {
  name: 'strip-html-comments',
  transformIndexHtml: { order: 'post', handler: (html) => html.replace(/<!--[\s\S]*?-->\n?/g, '') },
};

export default defineConfig({
  plugins: [stripHtmlComments],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': api, '/media': api },
  },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true },
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 1000 }, // three.js is ~600 kB
});
