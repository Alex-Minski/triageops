import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// amazon-cognito-identity-js expects Node's `global`; alias it to the browser's globalThis.
export default defineConfig({
  plugins: [react()],
  define: { global: 'globalThis' },
});
