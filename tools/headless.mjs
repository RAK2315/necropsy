// Shared launcher for the headless test browser. The browser never writes outside its own temp profile:
//   - downloads are denied browser-wide before any page is opened (tests read blob bytes in the page instead);
//   - the profile directory is removed after the browser exits, on success, on error and on the watchdog timeout.
// The browser picks its own free debugging port (written to DevToolsActivePort in the profile), so two test browsers
// running at once can never talk to each other's DevTools.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const EXES = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const findBrowser = () => EXES.find(existsSync) || null;

/**
 * Start the browser with a fresh temp profile. Returns { port, proc, dir, close }.
 * prefix: temp-dir prefix ('brun-', 'shot-', ...); args: extra command-line flags; timeoutMs: watchdog, after which the
 * browser is closed, the profile removed and the process exits with an error line on stdout.
 */
export async function launch(prefix, args = [], { timeoutMs = 100000 } = {}) {
  const exe = findBrowser();
  const dir = mkdtempSync(join(tmpdir(), prefix));
  const proc = spawn(exe, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${dir}`,
    '--no-first-run', '--disable-gpu', '--disable-crash-reporter', '--no-default-browser-check', ...args, 'about:blank'],
    { stdio: 'ignore' });
  const exited = new Promise((r) => proc.once('exit', r));
  let control = null;            // the browser-target connection: holds the download denial, and closes the browser
  let closed = false;
  const close = async () => {
    if (closed) return;
    closed = true;
    // 1. graceful: Browser.close ends the browser and all its child processes
    if (control && control.readyState === 1) {
      try { control.send(JSON.stringify({ id: 99, method: 'Browser.close' })); } catch {}
    }
    await Promise.race([exited, sleep(8000)]);
    // 2. still running: end the whole process tree, not just the parent
    if (proc.exitCode === null && proc.signalCode === null) {
      if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(proc.pid), '/T', '/F'], { stdio: 'ignore' });
      else proc.kill('SIGKILL');
      await Promise.race([exited, sleep(5000)]);
    }
    try { control && control.close(); } catch {}
    // 3. remove the profile; child processes can hold files for a moment after the parent exits
    try {
      rmSync(dir, { recursive: true, force: true, maxRetries: 60, retryDelay: 250 });
    } catch (e) {
      process.stderr.write(`headless.mjs: could not remove the test profile ${dir}: ${e.message}\n`);
    }
  };
  const watchdog = setTimeout(async () => {
    console.log(JSON.stringify({ error: `browser run timed out after ${timeoutMs} ms` }));
    await close();
    process.exit(1);
  }, timeoutMs);
  watchdog.unref();
  const handle = { dir, proc, port: 0, close: async () => { clearTimeout(watchdog); await close(); } };
  try {
    handle.port = await activePort(dir, exited);
    control = await denyDownloads(handle.port);
  } catch (e) {
    await handle.close();
    throw e;
  }
  return handle;
}

/** The port the browser chose, from DevToolsActivePort in its own profile. */
async function activePort(dir, exited) {
  let gone = false;
  exited.then(() => { gone = true; });
  const f = join(dir, 'DevToolsActivePort');
  for (let i = 0; i < 120; i++) {
    if (gone) throw new Error('browser exited before opening DevTools');
    try {
      const port = Number(readFileSync(f, 'utf8').split('\n')[0]);
      if (port > 0) return port;
    } catch {}
    await sleep(100);
  }
  throw new Error('browser did not open DevTools');
}

/**
 * Browser.setDownloadBehavior must be sent on the browser target, not a page, and the browser resets it when that
 * connection closes, so the connection is returned and kept open until close(). A refusal is an error, never ignored.
 */
async function denyDownloads(port) {
  let version;
  for (let i = 0; i < 80 && !version; i++) {
    try { version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); } catch {}
    if (!version) await sleep(100);
  }
  if (!version) throw new Error('browser did not answer on its DevTools port');
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  const reply = await new Promise((r) => {
    ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id === 1) r(d); };
    ws.send(JSON.stringify({ id: 1, method: 'Browser.setDownloadBehavior', params: { behavior: 'deny' } }));
  });
  if (reply.error) { ws.close(); throw new Error('could not deny downloads: ' + reply.error.message); }
  return ws;
}
