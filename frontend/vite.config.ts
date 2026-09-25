import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // PWA нужна ради одного: установки на экран «Домой» у руководителя. Только после неё
    // iOS разрешает уведомления, а магазины приложений становятся не нужны (ADR-0030).
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'ORBITA',
        short_name: 'ORBITA',
        description: 'Что требует внимания сейчас',
        lang: 'ru',
        start_url: '/',
        display: 'standalone',
        // Цвета взяты из токенов светлой темы: экран запуска не должен вспыхивать белым
        // поверх приглушённой темы и наоборот.
        background_color: '#f6f7f9',
        theme_color: '#0b1220',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icon-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // Кешируется оболочка, а не данные. Данные обновляются опросом и обязаны быть
        // свежими: показанный из кеша просроченный срок — это неверное решение
        // руководителя, а не экономия сети.
        globPatterns: ['**/*.{js,css,html,svg,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/internal\//],
        runtimeCaching: [],
      },
      devOptions: { enabled: false },
    }),
  ],

  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },

  server: {
    port: 5173,
    // Backend поднимается отдельно (make dev). Прокси даёт тот же один источник, что
    // Netlify в облаке: cookie сессии работает так же, как в бою (ADR-0028).
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },

  preview: {
    port: 4173,
    // Тот же прокси для собранной сборки: в конвейере сценарии идут по ней, а не по
    // режиму разработки. Иначе проверялось бы то, чего в облаке нет.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },

  build: {
    // Предупреждение Vite считает несжатый размер и потому пугает впустую. Настоящий
    // бюджет — сжатый, его проверяет scripts/check-budget.mjs после сборки.
    chunkSizeWarningLimit: 600,
    // Манифест — карта кусков и их статических импортов. По нему бюджет отличает то, что
    // грузится при открытии, от того, что приезжает позже по переходу в раздел.
    manifest: true,
  },

  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    css: false,
    // Playwright живёт в e2e/ и запускается своей командой: vitest не должен пытаться
    // исполнить его сценарии.
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
});
