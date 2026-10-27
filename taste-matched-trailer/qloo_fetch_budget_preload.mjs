/** Derived from API-REELLE-01/physical-fetch-guard.cjs; one fail-closed run. */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const RUN_ID = /^run-[a-z0-9_-]{4,64}$/i;
const integer = (value, low, high) => Number.isSafeInteger(value) && value >= low && value <= high;

export function readPhysicalCounter(directory) {
  const config = JSON.parse(fs.readFileSync(path.join(directory, "config.json"), "utf8"));
  const state = JSON.parse(fs.readFileSync(path.join(directory, "counter.json"), "utf8"));
  if (config.schema_version !== 1 || !RUN_ID.test(config.run_id) ||
      !integer(config.max_attempts, 0, 14) || config.allowed_origin !== "https://hackathon.api.qloo.com" ||
      !integer(config.min_interval_ms, 2000, 90000) || !integer(config.active_ms_limit, 1, 120000) ||
      !integer(config.request_timeout_ms, 1, 15000) ||
      state.schema_version !== 1 || state.run_id !== config.run_id || state.limit !== config.max_attempts ||
      !integer(state.attempts, 0, state.limit) || !integer(state.active_ms, 0, Number.MAX_SAFE_INTEGER) ||
      !integer(state.last_started_ms, 0, Number.MAX_SAFE_INTEGER) ||
      !(state.halted === null || typeof state.halted === "string") ||
      !Array.isArray(state.events) || state.events.length !== state.attempts ||
      state.events.some((event, index) => event.attempt !== index + 1 || event.run_id !== state.run_id)) {
    throw new Error("QLOO_COUNTER_INVALID_NO_RESET");
  }
  return { config, state };
}

export function initialiseGuardRun(directory, runId, { maxAttempts = 8, activeMs = 120000 } = {}) {
  if (!integer(maxAttempts, 0, 14) || !integer(activeMs, 1, 120000)) throw new Error("INVALID_LOCAL_BUDGET");
  if (!RUN_ID.test(runId)) throw new Error("QLOO_RUN_ID_INVALID");
  // mkdir is exclusive. Existing, missing or corrupt state is never reset.
  fs.mkdirSync(path.dirname(directory), { recursive: true, mode: 0o700 });
  fs.mkdirSync(directory, { mode: 0o700 });
  const config = { schema_version: 1, run_id: runId, max_attempts: maxAttempts,
    allowed_origin: "https://hackathon.api.qloo.com", min_interval_ms: 2000,
    active_ms_limit: activeMs, request_timeout_ms: 15000 };
  const state = { schema_version: 1, run_id: runId, limit: maxAttempts, attempts: 0,
    active_ms: 0, last_started_ms: 0, halted: null, events: [] };
  for (const [name, value] of [["config.json", config], ["counter.json", state]]) {
    fs.writeFileSync(path.join(directory, name), JSON.stringify(value, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  }
  return directory;
}

export function createPhysicalBudgetFetch({ directory, baseFetch = globalThis.fetch,
    now = Date.now, pause = ms => new Promise(resolve => setTimeout(resolve, ms)), phaseDeadlineMs = null }) {
  if (phaseDeadlineMs !== null && (!Number.isSafeInteger(phaseDeadlineMs) || phaseDeadlineMs<0)) throw new Error("INVALID_FAMILY_DEADLINE");
  const phaseRemaining=()=>phaseDeadlineMs===null?Infinity:phaseDeadlineMs-now();
  const { config, state } = readPhysicalCounter(directory);
  const lockPath = path.join(directory, "active.lock");
  const token = crypto.randomUUID();
  const fd = fs.openSync(lockPath, "wx", 0o600);
  fs.writeFileSync(fd, JSON.stringify({ pid: process.pid, run_id: state.run_id, token }));
  fs.closeSync(fd);
  const statePath = path.join(directory, "counter.json");
  const save = () => {
    const temporary = `${statePath}.${process.pid}.${token}.tmp`;
    fs.writeFileSync(temporary, JSON.stringify(state, null, 2) + "\n", { mode: 0o600 });
    fs.renameSync(temporary, statePath);
  };
  const release = () => {
    try { if (JSON.parse(fs.readFileSync(lockPath, "utf8")).token === token) fs.unlinkSync(lockPath); } catch {}
  };
  const interrupt = () => {
    if (state.events.some(event => event.outcome === "in_flight")) {
      state.halted = "UNKNOWN_OUTCOME_NO_RETRY";
      try { save(); } catch {}
    }
    release();
    process.exit(0);
  };
  process.on("exit", release);
  process.on("SIGTERM", interrupt);
  let chain = Promise.resolve();
  let closed = false;
  const secret = process.env.QLOO_API_KEY || "";
  const redact = value => secret ? String(value).split(secret).join("[REDACTED]") : String(value);
  const fetch = (input, options = {}) => {
    const pending = chain.then(async () => {
      if (closed) throw new Error("QLOO_GUARD_CLOSED");
      if (phaseRemaining()<=0) throw new Error("QLOO_FAMILY_ACTIVE_DEADLINE");
      const disk = readPhysicalCounter(directory).state;
      if (JSON.stringify(disk) !== JSON.stringify(state)) throw new Error("QLOO_COUNTER_EPOCH_CHANGED");
      const url = new URL(typeof input === "string" || input instanceof URL ? String(input) : input.url);
      const method = String(options.method || input?.method || "GET").toUpperCase();
      if (url.origin !== config.allowed_origin || method !== "GET" || url.username || url.password ||
          [...url.searchParams.keys()].some(key => /api.?key|token|authorization/i.test(key))) {
        throw new Error("QLOO_TRANSPORT_SCOPE_REFUSED");
      }
      if (state.halted || state.attempts >= config.max_attempts || state.active_ms >= config.active_ms_limit) {
        throw new Error("QLOO_RUN_BUDGET_CLOSED");
      }
      const wait = state.last_started_ms ? Math.max(0, config.min_interval_ms - (now() - state.last_started_ms)) : 0;
      if (wait>=phaseRemaining()) throw new Error("QLOO_FAMILY_ACTIVE_DEADLINE");
      if (state.active_ms + wait >= config.active_ms_limit) throw new Error("QLOO_RUN_DEADLINE");
      if (wait) { await pause(wait); state.active_ms += wait; }
      if (phaseRemaining()<=0) throw new Error("QLOO_FAMILY_ACTIVE_DEADLINE");
      const start = now();
      const row = { run_id: state.run_id, attempt: ++state.attempts, method, host: url.host,
        path: url.pathname, query: redact(url.search), requested_at: new Date(start).toISOString(), outcome: "in_flight" };
      state.last_started_ms = start;
      state.events.push(row);
      save(); // Reservation is durable before any call to the real transport.
      const abort = new AbortController();
      const upstream = options.signal || input?.signal;
      const cancel = () => abort.abort();
      if (upstream?.aborted) cancel(); else upstream?.addEventListener("abort", cancel, { once: true });
      const timer = setTimeout(cancel, Math.max(1,Math.min(config.request_timeout_ms, config.active_ms_limit - state.active_ms,phaseRemaining())));
      try {
        const response = await baseFetch(input, { ...options, method, redirect: "error", signal: abort.signal });
        const raw = await response.clone().text();
        const clean = redact(raw);
        row.status = response.status;
        row.response_sha256 = crypto.createHash("sha256").update(raw).digest("hex");
        row.redacted_response_sha256 = crypto.createHash("sha256").update(clean).digest("hex");
        row.response_bytes = Buffer.byteLength(raw);
        row.outcome = "response_received";
        fs.writeFileSync(path.join(directory, `http-${String(row.attempt).padStart(2, "0")}-response.txt`), clean, { flag: "wx", mode: 0o600 });
        try { JSON.parse(raw); } catch { state.halted = "INVALID_JSON_NO_RETRY"; }
        if (!response.ok) state.halted = `HTTP_${response.status}`;
        if (["ratelimit-remaining", "x-ratelimit-remaining"].some(name => response.headers.get(name) === "0")) state.halted = "SERVER_QUOTA_EXHAUSTED";
        return response;
      } catch {
        row.outcome = "network_outcome_unknown";
        state.halted = "UNKNOWN_OUTCOME_NO_RETRY";
        throw new Error("QLOO_TRANSPORT_FAILED_NO_RETRY");
      } finally {
        clearTimeout(timer);
        upstream?.removeEventListener("abort", cancel);
        row.duration_ms = Math.max(0, now() - start);
        state.active_ms += row.duration_ms;
        save();
      }
    });
    chain = pending.then(() => {}, () => {});
    return pending;
  };
  fetch.close = async () => {
    await chain;
    closed = true;
    process.removeListener("exit", release);
    process.removeListener("SIGTERM", interrupt);
    release();
  };
  return fetch;
}

if (process.env.QLOO_PHYSICAL_GUARD_INSTALL === "1") {
  // Metadata-only MCP processes may not have a run directory; their transport stays closed.
  globalThis.fetch = process.env.QLOO_GUARD_DIR
    ? createPhysicalBudgetFetch({ directory: process.env.QLOO_GUARD_DIR, baseFetch: globalThis.fetch.bind(globalThis),
        phaseDeadlineMs:process.env.QLOO_GUARD_PHASE_DEADLINE_MS===undefined?null:Number(process.env.QLOO_GUARD_PHASE_DEADLINE_MS) })
    : async () => { throw new Error("QLOO_OFFLINE_TRANSPORT_REFUSED"); };
}
