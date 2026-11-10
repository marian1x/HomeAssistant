// Format conversion only; generated originals remain in src/assets.
import { readFile, writeFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';
const browser = await chromium.launch({channel: 'msedge'});
try {
  const page = await browser.newPage();
  for (const stem of ['interior', 'pendants']) {
    const source = (await readFile(`src/assets/${stem}.png`)).toString('base64');
    const result = await page.evaluate(async source => {
      const img = new Image();
      img.src = `data:image/png;base64,${source}`;
      await img.decode();
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext('2d').drawImage(img, 0, 0);
      return canvas.toDataURL('image/webp', .88).split(',')[1];
    }, source);
    await writeFile(`src/assets/${stem}.webp`, Buffer.from(result, 'base64'));
    console.log(stem, Buffer.from(result, 'base64').length);
  }
} finally { await browser.close(); }
