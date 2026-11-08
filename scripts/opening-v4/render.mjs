// Render opening.html frame-by-frame in headless Chromium.
//   --mode preview --times 0.8,3.4 --output dir   -> PNG stills
//   --mode video --output file.mp4                -> silent 1080p24 H.264
// Env: PLAYWRIGHT_CORE (path to playwright-core index.mjs), CHROME_PATH (optional executable).
import {spawn} from 'node:child_process';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const {chromium} = await import(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const cues = JSON.parse(await readFile(path.resolve(root, opt('cues', 'demo/opening-v4/voice-cues.json'))));
const mode = opt('mode', 'preview');
const fps = 24;

const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || undefined});
const page = await browser.newPage({viewport: {width: 1920, height: 1080}});
await page.goto(pathToFileURL(path.join(here, 'opening.html')).href);
await page.evaluate(c => window.setCues(c), cues);
const frame = async t => Buffer.from(await page.evaluate(t => window.frameData(t), t), 'base64');

if (mode === 'preview') {
  const out = path.resolve(root, opt('output', 'demo/opening-v4/visuals'));
  await mkdir(out, {recursive: true});
  for (const t of opt('times', '0.8,3.4,6.6,10.9,14.6,19,24.3,27.1,29.6,33,35.4').split(',').map(Number)) {
    await writeFile(path.join(out, `t${t.toFixed(2)}.png`), await frame(t));
  }
} else {
  const outFile = path.resolve(root, opt('output', 'demo/opening-v4/visuals/opening-silent.mp4'));
  await mkdir(path.dirname(outFile), {recursive: true});
  const ff = spawn((process.env.FFMPEG || 'ffmpeg'), ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe',
    '-framerate', String(fps), '-vcodec', 'png', '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'medium',
    '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', outFile], {stdio: ['pipe', 'inherit', 'inherit']});
  const total = Math.ceil(cues.end * fps);
  const started = Date.now();
  for (let i = 0; i < total; i++) {
    const buf = await frame(i / fps);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 96 === 0) console.log(`frame ${i}/${total} ${((Date.now() - started) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end();
  await new Promise((res, rej) => ff.on('close', c => c ? rej(new Error('ffmpeg ' + c)) : res()));
  console.log('wrote', outFile);
}
await browser.close();
