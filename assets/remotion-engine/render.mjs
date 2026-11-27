// Cầu nối CapCut Draft Studio → Remotion. Mỗi dòng stdout là một JSON (tool đọc để báo tiến độ).
//
//   node render.mjs ensure  [--fallback <đường dẫn trình duyệt> ...]
//   node render.mjs render  <jobs.json>
//
// jobs.json = {"browser": null | "<exe>", "fallbacks": ["<exe>", ...],
//              "jobs": [{"comp": "Term", "props": {...}, "out": "<file .mov>"}]}
// Clip ra ProRes 4444 có kênh alpha (CapCut nhận nền trong suốt của định dạng này).
import {existsSync, readFileSync, renameSync, rmSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const say = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
const msg = (e) => String((e && (e.message || e.stack)) || e).split('\n').slice(0, 6).join(' | ');

async function pickBrowser(explicit, fallbacks) {
  const {ensureBrowser} = await import('@remotion/renderer');
  if (explicit && existsSync(explicit)) return {path: explicit, kind: 'chosen'};
  try {
    let downloading = false;
    // Lỗi mạng khi tải có thể nổ ra ngoài promise (sự kiện 'error' của luồng tải) → bắt lại
    // để chuyển sang trình duyệt dự phòng thay vì làm sập tiến trình.
    let escape;
    const escaped = new Promise((_, rej) => (escape = rej));
    const onCrash = (e) => escape(e);
    process.on('uncaughtException', onCrash);
    process.on('unhandledRejection', onCrash);
    const st = await Promise.race([escaped, ensureBrowser({
      logLevel: 'error',
      onBrowserDownload: () => {
        downloading = true;
        say({event: 'download', p: 0});
        return {
          version: null,
          onProgress: ({percent, downloadedBytes, totalSizeInBytes}) =>
            say({event: 'download', p: percent, done: downloadedBytes, total: totalSizeInBytes}),
        };
      },
    })]).finally(() => {
      process.off('uncaughtException', onCrash);
      process.off('unhandledRejection', onCrash);
    });
    return {path: (st && st.path) || null, kind: 'headless-shell', downloaded: downloading};
  } catch (e) {
    say({event: 'warn', text: 'Không tải được Chrome Headless Shell của Remotion: ' + msg(e)});
  }
  for (const f of fallbacks || []) {
    if (f && existsSync(f)) return {path: f, kind: 'system'};
  }
  throw new Error('Không có trình duyệt để Remotion vẽ khung hình (không tải được Chrome Headless Shell, không thấy Chrome / Edge trên máy)');
}

async function ensure(args) {
  const fallbacks = [];
  for (let i = 0; i < args.length; i++) if (args[i] === '--fallback') fallbacks.push(args[++i]);
  const b = await pickBrowser(null, fallbacks);
  say({event: 'browser', ...b});
}

async function render(file) {
  const spec = JSON.parse(readFileSync(file, 'utf8'));
  const {bundle} = await import('@remotion/bundler');
  const {openBrowser, renderMedia, selectComposition} = await import('@remotion/renderer');
  const b = await pickBrowser(spec.browser, spec.fallbacks);
  say({event: 'browser', ...b});
  const t0 = Date.now();
  const serveUrl = await bundle({
    entryPoint: path.join(here, 'src', 'index.js'),
    publicDir: path.join(here, 'public'),
    onProgress: () => {},
  });
  say({event: 'bundled', sec: (Date.now() - t0) / 1000});
  const browser = await openBrowser('chrome', {
    browserExecutable: b.kind === 'headless-shell' ? null : b.path,
    logLevel: 'error',
  });
  let ok = 0;
  try {
    for (let i = 0; i < spec.jobs.length; i++) {
      const job = spec.jobs[i];
      const part = job.out + '.part.mov';
      const s = Date.now();
      say({event: 'start', i, n: spec.jobs.length, comp: job.comp});
      try {
        const composition = await selectComposition({
          serveUrl, id: job.comp, inputProps: job.props, puppeteerInstance: browser, logLevel: 'error',
        });
        await renderMedia({
          composition,
          serveUrl,
          inputProps: job.props,
          codec: 'prores',
          proResProfile: '4444',
          imageFormat: 'png',
          pixelFormat: 'yuva444p10le',
          muted: true,
          outputLocation: part,
          puppeteerInstance: browser,
          overwrite: true,
          logLevel: 'error',
          onProgress: ({progress}) => say({event: 'progress', i, p: progress}),
        });
        renameSync(part, job.out);
        ok++;
        say({event: 'done', i, out: job.out, sec: (Date.now() - s) / 1000, frames: composition.durationInFrames});
      } catch (e) {
        try { rmSync(part, {force: true}); } catch {}
        say({event: 'fail', i, error: msg(e)});
      }
    }
  } finally {
    await browser.close({silent: true}).catch(() => {});
  }
  say({event: 'finished', ok, n: spec.jobs.length});
}

const [cmd, ...rest] = process.argv.slice(2);
try {
  if (cmd === 'ensure') await ensure(rest);
  else if (cmd === 'render') await render(rest[0]);
  else if (cmd === 'version') {
    const pkg = JSON.parse(readFileSync(path.join(here, 'node_modules', 'remotion', 'package.json'), 'utf8'));
    say({event: 'version', remotion: pkg.version, node: process.version});
  } else throw new Error('Lệnh không đúng: ' + cmd);
} catch (e) {
  say({event: 'error', error: msg(e)});
  process.exitCode = 1;
}
