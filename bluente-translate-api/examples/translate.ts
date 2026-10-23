/**
 * Translate one document with the Bluente API (Node.js 18+, no dependencies).
 *
 * Flow: upload -> wait for SERVICE_PROCESSED -> validate_options (free dry run)
 * -> translate (charges credits) -> wait for READY -> download.
 *
 * Usage:
 *   BLUENTE_API_KEY=sk-... npx tsx translate.ts contract.docx en fr [out_dir]
 *
 * Server-side only: never ship the API key to a browser.
 */

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { basename, extname, join } from "node:path";

const BASE = "https://api.bluente.com/api/20250924/blu_translate";
const FAILED_STATES = new Set(["ERROR", "CANCELLED", "CREDITS_INSUFFICIENT"]);

const apiKey = process.env.BLUENTE_API_KEY;
if (!apiKey) throw new Error("Set BLUENTE_API_KEY");
// Build the header from the variable. A literal "Bearer $BLUENTE_API_KEY" string would send the text "$BLUENTE_API_KEY".
const AUTH = { Authorization: `Bearer ${apiKey}` };
const ENGINE = process.env.BLUENTE_ENGINE ?? "3";

class BluenteError extends Error {
  constructor(public code: number | null, message: string, public data?: unknown) {
    super(`Bluente API error ${code}: ${message}`);
  }
}

interface Envelope<T> {
  code: number;
  message: string;
  data?: T;
}

// Every JSON response is HTTP 200; success is only code === 0.
async function unwrap<T>(res: Response): Promise<T> {
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new BluenteError(null, `non-JSON response (HTTP ${res.status})`);
  }
  if (body.code !== 0) throw new BluenteError(body.code, body.message, body.data);
  return body.data as T;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function upload(path: string): Promise<number> {
  const form = new FormData();
  // The filename (with extension) tells Bluente the file type. Don't set Content-Type yourself.
  form.append("file", new Blob([await readFile(path)]), basename(path));
  const res = await fetch(`${BASE}/upload?engine=${ENGINE}`, { method: "POST", headers: AUTH, body: form });
  const data = await unwrap<{ id: number }>(res);
  return data.id;
}

interface CheckData {
  id: number;
  status: string;
  message: string;
  pageCount: number;
}

async function check(id: number): Promise<CheckData> {
  const res = await fetch(`${BASE}/check?id=${id}`, { headers: AUTH });
  return unwrap<CheckData>(res);
}

async function waitFor(id: number, wanted: string, timeoutMs: number, intervalMs: number): Promise<CheckData> {
  const deadline = Date.now() + timeoutMs;
  let transientFailures = 0;
  for (;;) {
    try {
      const data = await check(id);
      transientFailures = 0;
      if (data.status === wanted) return data;
      if (FAILED_STATES.has(data.status)) {
        throw new BluenteError(null, `task ${id} stopped: ${data.status} - ${data.message}`, data);
      }
      console.error(`  status: ${data.status}`);
    } catch (err) {
      const transient =
        err instanceof TypeError || // network error from fetch
        (err instanceof BluenteError && err.code === 500 && !err.message.includes("record not found"));
      if (!transient) throw err;
      if (++transientFailures >= 5) throw new BluenteError(null, "too many consecutive /check failures");
    }
    if (Date.now() >= deadline) throw new BluenteError(null, `timed out waiting for ${wanted} (task ${id})`);
    await sleep(intervalMs);
  }
}

async function postJson(path: string, body: unknown): Promise<void> {
  const res = await fetch(`${BASE}${path}?engine=${ENGINE}`, {
    method: "POST",
    headers: { ...AUTH, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await unwrap<unknown>(res);
}

function filenameFromDisposition(value: string | null): string | null {
  if (!value) return null;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(value);
  if (star) return decodeURIComponent(star[1].trim());
  const plain = /filename="([^"]*)"/i.exec(value);
  if (plain) return decodeURIComponent(plain[1].replace(/\+/g, "%20"));
  return null;
}

async function download(id: number, outDir: string, fallbackName: string): Promise<string> {
  const res = await fetch(`${BASE}/download?id=${id}`, { headers: AUTH });
  // Errors come back as JSON with HTTP 200, not as a file.
  if ((res.headers.get("content-type") ?? "").startsWith("application/json")) {
    await unwrap<unknown>(res); // throws with the server's code and message
    throw new BluenteError(null, "expected a file but got JSON");
  }
  const name = basename(filenameFromDisposition(res.headers.get("content-disposition")) ?? fallbackName);
  const out = join(outDir, name);
  await writeFile(out, Buffer.from(await res.arrayBuffer()));
  return out;
}

async function main(): Promise<void> {
  const [path, from, to, outDir = "."] = process.argv.slice(2);
  if (!path || !from || !to) {
    console.error("usage: translate.ts <file> <from> <to> [out_dir]");
    process.exit(2);
  }
  await mkdir(outDir, { recursive: true });

  const id = await upload(path);
  console.error(`Task id: ${id}`);
  await waitFor(id, "SERVICE_PROCESSED", 15 * 60_000, 5_000);

  const request = { id, action: "start", from, to, meta_data: { source_file: basename(path) } };
  await postJson("/validate_options", request); // free dry run
  await postJson("/translate", request); // charges credits

  await waitFor(id, "READY", 60 * 60_000, 15_000);
  const fallback = `${basename(path, extname(path))}.${to}${extname(path)}`;
  console.log(await download(id, outDir, fallback));
}

main().catch((err) => {
  console.error(err instanceof BluenteError ? `error: ${err.message}` : err);
  if (err instanceof BluenteError && err.data) console.error("details:", err.data);
  process.exit(1);
});
