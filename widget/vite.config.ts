import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

// IIFE build: produces a single self-contained <script>-droppable bundle at
// dist/gktuition-tutor.iife.js. The WordPress plugin enqueues this file and
// calls window.GKTuitionTutor.mount() once the DOM is ready.
export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/Widget.tsx'),
      name: 'GKTuitionTutor',
      formats: ['iife'],
      fileName: () => 'gktuition-tutor.iife.js',
    },
    rollupOptions: {
      // React + ReactDOM are bundled in — the host site is WordPress and we
      // can't assume it ships a compatible React. Cost: ~45KB gzip for the
      // React runtime, well inside the 200KB budget.
      output: {
        inlineDynamicImports: true,
        assetFileNames: 'gktuition-tutor.[ext]',
      },
    },
    cssCodeSplit: false,
    sourcemap: false,
    minify: 'esbuild',
    target: 'es2020',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    css: false,
  },
});
