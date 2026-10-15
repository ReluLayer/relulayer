import { copyFile, constants } from 'node:fs/promises';
import { resolve } from 'node:path';

/**
 * Astro sitemap generates `sitemap-index.xml` (hyphen). Google Search Console
 * and some legacy submissions may request `sitemap_index.xml` (underscore).
 * This post-build step copies the hyphenated sitemap to the underscore variant
 * so both URLs return 200 on any static host (Nginx, Cloudflare Pages, etc.).
 */

const outputs = [
  'dist',
  'relulayer-site',
];

for (const output of outputs) {
  const src = resolve(output, 'sitemap-index.xml');
  const dest = resolve(output, 'sitemap_index.xml');
  try {
    await copyFile(src, dest, constants.COPYFILE_FICLONE);
    console.log(`✓ Copied ${src} -> ${dest}`);
  } catch (err) {
    console.error(`✗ Failed to copy ${src}: ${err.message}`);
    process.exitCode = 1;
  }
}
