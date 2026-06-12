import { expect, test } from 'playwright/test';
import { writeJsonArtifact } from './ux-artifacts';

const baseUrl = process.env.BASE_URL?.trim() || 'https://chummer.run';

test('homepage and ledger routes use the globe as the primary render surface', async ({ page }) => {
  const results: Array<Record<string, unknown>> = [];
  const expectations = {
    '/': {
      poster: /black-ledger-video-globe-idle-poster\.png(?:\?.*)?$/,
      mp4: /black-ledger-video-globe-idle\.mp4(?:\?.*)?$/,
      mapRender: true,
      renderer: /^(canvas-geoscape|webgl-geoscape)$/,
      videoLayer: /^(first-party-raster-overlay|canvas-only)$/,
    },
    '/ledger': {
      poster: /(turn-2-newsreel-poster\.png|black-ledger-video-globe-idle-poster\.png)(?:\?.*)?$/,
      mp4: /(turn-2-newsreel\.mp4|black-ledger-video-globe-idle\.mp4)(?:\?.*)?$/,
      mapRender: false,
      renderer: "magicfit-newsreel",
      videoLayer: /^(magicfit-newsreel)$/,
    },
    '/ledger/map': {
      poster: /black-ledger-video-globe-idle-poster\.png(?:\?.*)?$/,
      mp4: /black-ledger-video-globe-idle\.mp4(?:\?.*)?$/,
      mapRender: true,
      renderer: /^(canvas-geoscape|webgl-geoscape)$/,
      videoLayer: /^(first-party-raster-overlay|canvas-only)$/,
    },
  };
  for (const route of ['/', '/ledger', '/ledger/map']) {
    const expectation = expectations[route as keyof typeof expectations];
    await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded' });
    const root = page.locator('[data-black-ledger-geoscape-root]').first();
    await expect(root).toHaveAttribute('data-ready', 'true');
    await expect(root.locator('canvas.black-ledger-geoscape__canvas')).toBeVisible();
    await expect(root.locator('canvas.black-ledger-geoscape__webgl')).toBeVisible();
    await expect(root.locator('video.black-ledger-geoscape__video-plate')).toHaveAttribute('poster', expectation.poster);
    await expect(root.locator('video.black-ledger-geoscape__video-plate source[type="video/mp4"]')).toHaveAttribute('src', expectation.mp4);
    const videoState = await root.getAttribute('data-video-globe');
    const qaRenderer = await root.getAttribute('data-qa-renderer');
    expect(videoState === 'ready' || (videoState === 'disabled' && qaRenderer === 'canvas-only')).toBeTruthy();
    await page.waitForTimeout(250);
    const pixelProbe = await root.evaluate((element) => {
      const overlayCanvas = element.querySelector('canvas.black-ledger-geoscape__canvas') as HTMLCanvasElement | null;
      const webglCanvas = element.querySelector('canvas.black-ledger-geoscape__webgl') as HTMLCanvasElement | null;
      const overlayContext = overlayCanvas?.getContext('2d', { willReadFrequently: true });
      const overlayWidth = overlayCanvas?.width ?? 0;
      const overlayHeight = overlayCanvas?.height ?? 0;
      let coloredPixels = 0;
      let alphaPixels = 0;
      if (overlayContext && overlayWidth > 0 && overlayHeight > 0) {
        const sampleWidth = Math.min(overlayWidth, 420);
        const sampleHeight = Math.min(overlayHeight, 320);
        const imageData = overlayContext.getImageData(0, 0, sampleWidth, sampleHeight).data;
        for (let index = 0; index < imageData.length; index += 16) {
          const red = imageData[index] ?? 0;
          const green = imageData[index + 1] ?? 0;
          const blue = imageData[index + 2] ?? 0;
          const alpha = imageData[index + 3] ?? 0;
          if (alpha > 12) {
            alphaPixels += 1;
          }
          if (alpha > 20 && Math.max(red, green, blue) - Math.min(red, green, blue) > 12) {
            coloredPixels += 1;
          }
        }
      }

      return {
        overlayWidth,
        overlayHeight,
        webglWidth: webglCanvas?.width ?? 0,
        webglHeight: webglCanvas?.height ?? 0,
        coloredPixels,
        alphaPixels,
        renderer: (element as HTMLElement).dataset.renderer ?? '',
        videoLayer: (element as HTMLElement).dataset.videoLayer ?? '',
      };
    });
    expect(pixelProbe.overlayWidth).toBeGreaterThan(300);
    expect(pixelProbe.overlayHeight).toBeGreaterThan(260);
    expect(pixelProbe.webglWidth).toBeGreaterThan(300);
    expect(pixelProbe.webglHeight).toBeGreaterThan(260);
    if (expectation.mapRender) {
      expect(pixelProbe.alphaPixels).toBeGreaterThan(250);
      expect(pixelProbe.coloredPixels).toBeGreaterThan(80);
      expect(pixelProbe.renderer).not.toBe('video-globe-overlay');
      expect(pixelProbe.videoLayer).toMatch(expectation.videoLayer);
      expect(pixelProbe.renderer).toMatch(expectation.renderer);
    } else {
      expect(pixelProbe.coloredPixels).toBeLessThan(24);
      expect(pixelProbe.alphaPixels).toBeLessThan(24);
      expect(pixelProbe.renderer).toBe(expectation.renderer);
      expect(pixelProbe.videoLayer).toContain('newsreel');
    }
    const box = await root.boundingBox();
    results.push({
      route,
      renderer: await root.getAttribute('data-renderer'),
      video_globe: await root.getAttribute('data-video-globe'),
      pixel_probe: pixelProbe,
      ready: await root.getAttribute('data-ready'),
      height: box?.height ?? 0,
    });
  }

  writeJsonArtifact('BLACK_LEDGER_GLOBE_RENDER.generated.json', {
    generated_at_utc: new Date().toISOString(),
    status: 'pass',
    base_url: baseUrl,
    results,
  });
});
