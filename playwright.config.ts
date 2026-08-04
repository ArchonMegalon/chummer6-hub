import { defineConfig } from 'playwright/test';

const channel = process.env.CHUMMER_PLAYWRIGHT_CHANNEL?.trim();

export default defineConfig({
  workers: 1,
  use: {
    ...(channel ? { channel } : {}),
    headless: true,
    launchOptions: {
      args: ['--disable-quic'],
    },
  },
});
