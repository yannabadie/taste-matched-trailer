#!/usr/bin/env node
/**
 * Cultural Launch Director — Local Stdio MCP Backend & HTTP Bridge (`qloo_mcp_backend.mjs`)
 * =========================================================================================
 *
 * Aligns with the official Qloo Hackathon Kit (`https://github.com/qloo/qloo-hackathon-kit`)
 * and the locally installed `@qloo/qloo-harness@0.1.26` package:
 * - Installed binary: `~/Library/Application Support/Agentique/qloo-harness-0.1.26/node_modules/.bin/qloo`
 * - Contract version `1.0.0`, checksum `sha256:762bdcc5e14ff797b6de739d2658a83f78af35e68d7a5a3449455be6046924f5`,
 *   result schema `1.0-preview.1`.
 * - Exposes the 10 canonical MCP tools (`qloo_find` does NOT exist; `qloo_describe` resolves an entity;
 *   `qloo_rank` ranks `options` of short `option_type` with optional `signals`).
 * - Connects Browser (`index.html`) -> Local HTTP Server (`http://127.0.0.1:8787`, `/api/qloo-harness` & `/api/director/run`)
 *   -> Official Qloo Harness (`qloo mcp` stdio) -> Deterministic Rank/Decision/Brief/Export (`cultural_launch_director.py`)
 *   -> Redacted execution proof (`var/runs/last-run-receipt.json`).
 * - NEVER accepts, expects, logs, or echoes a Qloo API key from/to the browser.
 *
 * Usage:
 *   node qloo_mcp_backend.mjs --check-only              # Offline readiness + live stdio contract discovery (0 network calls)
 *   node qloo_mcp_backend.mjs --serve --port 8787       # Start local HTTP server at http://127.0.0.1:8787
 */

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import crypto from "node:crypto";
import { initialiseGuardRun, readPhysicalCounter } from "./qloo_fetch_budget_preload.mjs";
import { buildMovieRecommendArgs,buildMovieProposal,chooseMovieProposal } from "./movie_proposal.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export const BACKEND_ADAPTER_VERSION = "2.7.0-propose-confirm-20261027";
export const FETCH_BUDGET_PRELOAD_PATH = path.join(__dirname, "qloo_fetch_budget_preload.mjs");
export const FETCH_BUDGET_PRELOAD_URL = pathToFileURL(FETCH_BUDGET_PRELOAD_PATH).href;
export const INSTALLED_HARNESS_ROOT =
  process.env.QLOO_HARNESS_ROOT ||
  path.join(os.homedir(), "Library/Application Support/Agentique/qloo-harness-0.1.26");
export const INSTALLED_HARNESS_BIN =
  process.env.QLOO_HARNESS_BIN ||
  path.join(INSTALLED_HARNESS_ROOT, "node_modules", ".bin", "qloo");
export const INSTALLED_HARNESS_DIST_BIN = path.join(
  INSTALLED_HARNESS_ROOT,
  "node_modules",
  "@qloo",
  "qloo-harness",
  "dist",
  "bin.js"
);

export const CANONICAL_TEN_TOOLS = Object.freeze([
  "qloo_capabilities",
  "qloo_recommend",
  "qloo_rank",
  "qloo_describe",
  "qloo_where_popular",
  "qloo_compare_audiences",
  "qloo_entity_tags",
  "qloo_audience_demographics",
  "qloo_trends",
  "qloo_find_tags",
]);

export const QLOO_RANK_OPTION_TYPES = Object.freeze([
  "artist",
  "book",
  "brand",
  "movie",
  "person",
  "place",
  "podcast",
  "tv_show",
  "videogame",
]);

export const QLOO_DESCRIBE_ENTITY_TYPES = Object.freeze([
  "artist",
  "book",
  "brand",
  "movie",
  "person",
  "place",
  "podcast",
  "tv_show",
  "videogame",
  "locality",
  "actor",
  "album",
  "author",
  "director",
]);

export const PINNED_REQUIREMENTS = Object.freeze({
  nodeMinVersion: "22.19.0",
  qlooHarnessMinVersion: "0.1.26",
  contractVersion: "1.0.0",
  contractChecksum: "sha256:762bdcc5e14ff797b6de739d2658a83f78af35e68d7a5a3449455be6046924f5",
  resultSchemaVersion: "1.0-preview.1",
  mcpProtocolVersion: "2024-11-05",
  installedHarnessBin: INSTALLED_HARNESS_BIN,
  mcpArgs: ["mcp"],
  canonicalTools: CANONICAL_TEN_TOOLS,
  allowedStatuses: ["ok", "empty", "needs_input", "partial", "degraded", "error"],
  budgetLimits: {
    qlooNetworkAttemptLimit: 8,
    maxRetriesPerCall: 1,
    maxInFlight: 2,
    toolTimeoutMs: 15000,
    activeTimeLimitMs: 90000,
  },
});

const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const SECRET_RE = /(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]+|X-Api-Key\s*[:=]\s*[A-Za-z0-9._-]+)/gi;

export function redactText(input) {
  return String(input ?? "")
    .replace(EMAIL_RE, "[REDACTED_EMAIL]")
    .replace(SECRET_RE, "[REDACTED_CREDENTIAL]")
    .trim();
}

export function checkNodeVersion(versionStr = process.versions.node) {
  const [maj, min] = String(versionStr).split(".").map((n) => Number.parseInt(n, 10) || 0);
  const ok = maj > 22 || (maj === 22 && min >= 19);
  return {
    nodeVersion: versionStr,
    requiredMin: PINNED_REQUIREMENTS.nodeMinVersion,
    supported: ok,
  };
}

export function resolveQlooMcpExecutable() {
  if (fs.existsSync(INSTALLED_HARNESS_BIN)) {
    return { command: INSTALLED_HARNESS_BIN, args: ["mcp"], source: "installed_agentique_harness_0.1.26" };
  }
  if (fs.existsSync(INSTALLED_HARNESS_DIST_BIN)) {
    return { command: process.execPath, args: [INSTALLED_HARNESS_DIST_BIN, "mcp"], source: "installed_agentique_dist_bin_0.1.26" };
  }
  const whichRes = spawnSync("which", ["qloo"], { encoding: "utf8" });
  if (whichRes.status === 0 && whichRes.stdout && whichRes.stdout.trim()) {
    return { command: whichRes.stdout.trim(), args: ["mcp"], source: "system_path" };
  }
  return { command: INSTALLED_HARNESS_BIN, args: ["mcp"], source: "not_found" };
}

export function checkQlooCliAvailable() {
  const resolved = resolveQlooMcpExecutable();
  return resolved.source !== "not_found";
}

/**
 * Builds the minimal child environment for `qloo mcp` stdio without leaking full `process.env`.
 */
export function buildSafeStdioEnv(sourceEnv = process.env) {
  const safe = {};
  for (const key of ["PATH", "HOME", "TMPDIR", "NODE_ENV", "LANG", "QLOO_API_KEY", "QLOO_BASE_URL", "QLOO_TRUSTED_BASE_URL", "QLOO_HOME", "QLOO_GUARD_DIR"]) {
    if (typeof sourceEnv[key] === "string" && sourceEnv[key].length > 0) {
      safe[key] = sourceEnv[key];
    }
  }
  return safe;
}

/**
 * Builds canonical `qloo_describe` arguments (`{ entity, type? }`, `additionalProperties: false`).
 */
export function buildCanonicalDescribeArgs(rawQuery) {
  const norm = String(rawQuery || "").trim();
  const lower = norm.toLowerCase();
  let explicitType = null;
  let cleanEntity = norm;
  if (lower.endsWith("(book)")) {
    explicitType = "book";
    cleanEntity = norm.slice(0, -"(book)".length).trim();
  } else if (lower.endsWith("(movie)") || lower.endsWith("(film)")) {
    explicitType = "movie";
    cleanEntity = norm.replace(/\((?:movie|film)\)$/i, "").trim();
  }
  cleanEntity = cleanEntity.replace(/\s*\(synthetic title\)$/i, "").trim();
  const args = { entity: redactText(cleanEntity) };
  if (explicitType && QLOO_DESCRIBE_ENTITY_TYPES.includes(explicitType)) {
    args.type = explicitType;
  }
  return args;
}

/**
 * Builds canonical `qloo_rank` arguments (`{ options, option_type, signals? }`, `additionalProperties: false`).
 * Never passes `shortlist_type`, `confirmed_entity_ids`, or `input_hash`.
 */
export function buildCanonicalRankArgs({ optionType, options, signals }) {
  let shortType = String(optionType || "")
    .trim()
    .toLowerCase()
    .replace(/^urn:entity:/, "");
  if (shortType === "film") shortType = "movie";
  if (!QLOO_RANK_OPTION_TYPES.includes(shortType)) {
    throw new Error(`Unsupported qloo_rank option_type '${shortType}'.`);
  }
  if (!Array.isArray(options) || !options.length || options.length>10) throw new Error("An explicit shortlist is required before rank");
  const cleanOptions = options
    .map((o) => redactText(o))
    .filter(Boolean)
    .slice(0, 10);
  const args = {
    options: cleanOptions,
    option_type: shortType,
  };
  if (Array.isArray(signals) && signals.length > 0) {
    const cleanSignals = signals.map((s) => redactText(s)).filter(Boolean).slice(0, 10);
    if (cleanSignals.length > 0) {
      args.signals = cleanSignals;
    }
  }
  return args;
}

/**
 * Normalizes any MCP tool response (`structuredContent` with `results` array, or legacy `results.entities`)
 * into one of the 6 documented statuses + `invalid_contract`.
 * Preserves `structuredContent`, `status`, `warnings`, and canonical `results` array.
 */
export function normalizeHarnessEnvelope(rawEnvelope, { hasServerKey = Boolean(process.env.QLOO_API_KEY && process.env.QLOO_API_KEY.trim()) } = {}) {
  if (!rawEnvelope || typeof rawEnvelope !== "object") {
    return {
      status: "invalid_contract",
      authentication_state: "not_checked",
      results: [],
      warnings: [],
      limitations: ["Malformed harness envelope."],
      error: { code: "MALFORMED_ENVELOPE", retryable: false, recovery: "Inspect pinned harness tool schema." },
      network_attempt_made: false,
    };
  }

  const sc =
    rawEnvelope.structuredContent && typeof rawEnvelope.structuredContent === "object"
      ? rawEnvelope.structuredContent
      : null;
  const sourceDoc = sc || rawEnvelope;

  const errObj = sourceDoc.error || rawEnvelope.error || null;
  const errCode = errObj && typeof errObj === "object" ? String(errObj.code || "") : "";

  const rawAuth = String(rawEnvelope.authentication_state || "");
  let authState = "not_checked";
  if (errCode === "QLOO_AUTH" || errCode === "AUTH_INVALID_OR_MISSING_KEY") {
    authState = "not_authenticated";
  } else if (["authenticated", "not_authenticated", "not_checked"].includes(rawAuth)) {
    authState = rawAuth;
  } else if (hasServerKey && sc && ["ok", "partial", "degraded", "empty", "needs_input"].includes(String(sourceDoc.status || ""))) {
    authState = "authenticated";
  }

  const rawWarnings = Array.isArray(sourceDoc.warnings)
    ? sourceDoc.warnings.map((w) => redactText(w)).filter(Boolean)
    : Array.isArray(rawEnvelope.warnings)
      ? rawEnvelope.warnings.map((w) => redactText(w)).filter(Boolean)
      : [];

  const rawLimitations = Array.isArray(rawEnvelope.limitations)
    ? rawEnvelope.limitations.map((item) => redactText(item)).filter(Boolean)
    : [];
  for (const w of rawWarnings) {
    const note = `MCP warning: ${w}`;
    if (!rawLimitations.includes(note)) {
      rawLimitations.push(note);
    }
  }

  const rawStatus = String(sourceDoc.status || rawEnvelope.status || "");
  if (!PINNED_REQUIREMENTS.allowedStatuses.includes(rawStatus)) {
    return {
      status: "invalid_contract",
      authentication_state: authState,
      results: [],
      warnings: rawWarnings,
      limitations: rawLimitations,
      structuredContent: sc || undefined,
      error: {
        code: "UNKNOWN_ENVELOPE_STATUS",
        retryable: false,
        recovery: `Status '${redactText(rawStatus)}' is not in the 6 documented harness statuses.`,
      },
      network_attempt_made: false,
    };
  }

  const isCanonicalList = Array.isArray(sourceDoc.results);
  const rawEntities = isCanonicalList
    ? sourceDoc.results
    : Array.isArray(sourceDoc?.results?.entities)
      ? sourceDoc.results.entities
      : [];

  const validEntities = rawEntities.filter(e=>e && typeof e==="object" && typeof (e.entity_id??e.id)==="string" && (e.entity_id??e.id).trim());
  if (rawStatus === "ok" && validEntities.length !== rawEntities.length) {
    return {status:"invalid_contract",authentication_state:authState,results:[],warnings:rawWarnings,
      limitations:[...rawLimitations,"The response contained items without an identity; a filtered subset is not a complete result."],
      structuredContent:sc || undefined,error:{code:"MALFORMED_RESULT_ITEMS",retryable:false},network_attempt_made:rawEnvelope.network_attempt_made!==false};
  }

  // `QLOO_AUTH` from `@qloo/qloo-harness` is rejected locally before any network call is made
  const networkAttemptMade =
    errCode === "QLOO_AUTH" && (!hasServerKey || sourceDoc?.execution?.duration_ms === 0)
      ? false
      : rawEnvelope.network_attempt_made !== false;

  if (rawStatus === "ok" && validEntities.length === 0) {
    return {
      status: "empty",
      authentication_state: authState,
      results: isCanonicalList ? [] : { entities: [] },
      warnings: rawWarnings,
      limitations: [
        ...rawLimitations,
        "Status 'ok' returned 0 valid items with IDs; treated as empty result requiring reformulation.",
      ],
      structuredContent: sc || undefined,
      error: null,
      network_attempt_made: networkAttemptMade,
    };
  }

  return {
    status: rawStatus,
    authentication_state: authState,
    results: isCanonicalList ? validEntities : { entities: validEntities },
    warnings: rawWarnings,
    limitations: rawLimitations,
    structuredContent: sc || undefined,
    error: errObj
      ? {
          code: redactText(errObj.code || "TOOL_ERROR"),
          layer: errObj.layer ? redactText(errObj.layer) : undefined,
          retryable: Boolean(errObj.retryable),
          recovery: redactText(errObj.recovery || ""),
        }
      : null,
    degradation_summary: sourceDoc.degradation_summary
      ? redactText(sourceDoc.degradation_summary)
      : rawEnvelope.degradation_summary
        ? redactText(rawEnvelope.degradation_summary)
        : null,
    network_attempt_made: networkAttemptMade,
  };
}

/**
 * Stdio JSON-RPC session wrapper for the installed `@qloo/qloo-harness@0.1.26` (`qloo mcp`).
 * Injects `qloo_fetch_budget_preload.mjs` via `NODE_OPTIONS=--import` so every physical HTTP
 * attempt inside `QlooClient` (including `/search`, `/entities`, `/v2/insights` and retries)
 * is counted and gated at the 8-attempt ceiling before network transport.
 */
export class QlooStdioSession {
  constructor(envOverride = null, { attemptLimit = PINNED_REQUIREMENTS.budgetLimits.qlooNetworkAttemptLimit, offlineOnly = false, activeTimeLimitMs = null } = {}) {
    if (activeTimeLimitMs !== null && (typeof activeTimeLimitMs !== "number" || !Number.isFinite(activeTimeLimitMs) || activeTimeLimitMs < 0 || activeTimeLimitMs > 120000)) throw new Error("Invalid remaining family time");
    this.deadlineAt = activeTimeLimitMs === null ? null : performance.now()+activeTimeLimitMs;
    this.wallDeadline = activeTimeLimitMs === null ? null : Math.floor(Date.now()+activeTimeLimitMs);
    this.proc = null;
    this.nextId = 1;
    this.pending = new Map();
    this.buffer = "";
    this.envOverride = envOverride;
    this.attemptLimit = attemptLimit;
    if (!Number.isSafeInteger(attemptLimit) || attemptLimit < 0 || attemptLimit > 14) throw new Error("Invalid physical attempt limit");
    this.toolCalls = [];
    this.offlineOnly = offlineOnly;
    this.counterFilePath = null;
    this.lastPhysicalHttpStats = { attempts: 0, limit: attemptLimit, events: [] };
    this.initialized = false;
  }

  start() {
    if (this.proc) return;
    const execSpec = resolveQlooMcpExecutable();
    const childEnv = buildSafeStdioEnv(this.envOverride || process.env);
    if (!this.offlineOnly) {
      if (!childEnv.QLOO_GUARD_DIR) throw new Error("Missing preallocated physical run directory");
      this.counterFilePath = path.join(childEnv.QLOO_GUARD_DIR, "counter.json");
      readPhysicalCounter(childEnv.QLOO_GUARD_DIR);
    } else {
      delete childEnv.QLOO_API_KEY;
      delete childEnv.QLOO_GUARD_DIR;
    }
    childEnv.QLOO_PHYSICAL_GUARD_INSTALL = "1";
    if (this.wallDeadline !== null) childEnv.QLOO_GUARD_PHASE_DEADLINE_MS=String(this.wallDeadline);
    childEnv.NODE_OPTIONS = `--import ${FETCH_BUDGET_PRELOAD_URL}`;

    this.proc = spawn(execSpec.command, execSpec.args, {
      stdio: ["pipe", "pipe", "pipe"],
      env: childEnv,
    });
    this.proc.stdout.on("data", (chunk) => {
      this.buffer += chunk.toString("utf8");
      let idx;
      while ((idx = this.buffer.indexOf("\n")) !== -1) {
        const line = this.buffer.slice(0, idx).trim();
        this.buffer = this.buffer.slice(idx + 1);
        if (!line) continue;
        try {
          const msg = JSON.parse(line);
          if (msg.id && this.pending.has(msg.id)) {
            const { resolve, reject, timer } = this.pending.get(msg.id);
            clearTimeout(timer);
            this.pending.delete(msg.id);
            if (msg.error) reject(new Error(redactText(msg.error.message || "MCP stdio error")));
            else resolve(msg.result);
          }
        } catch {
          // Ignore non-JSON diagnostic lines on stdout
        }
      }
    });
    this.proc.stderr.on("data", () => {});
    const stopPending = () => {
      for (const { reject, timer } of this.pending.values()) {
        clearTimeout(timer);
        reject(Object.assign(new Error("MCP process stopped; outcome requires settlement"), { retryable: false }));
      }
      this.pending.clear();
    };
    this.proc.on("error", stopPending);
    this.proc.on("exit", stopPending);
  }

  getPhysicalHttpStats() {
    if (this.offlineOnly && !this.counterFilePath) {
      return this.lastPhysicalHttpStats;
    }
    if (!this.counterFilePath) throw new Error("Physical counter unavailable; refusing transport");
    {
      const { state: parsed } = readPhysicalCounter(path.dirname(this.counterFilePath));
      const stats = {
        run_id: parsed.run_id,
        attempts: parsed.attempts,
        limit: parsed.limit,
        halted: parsed.halted,
        events: parsed.events,
      };
      this.lastPhysicalHttpStats = stats;
      return stats;
    }
  }

  async request(method, params = {}, timeoutMs = PINNED_REQUIREMENTS.budgetLimits.toolTimeoutMs) {
    if (this.deadlineAt !== null && performance.now() >= this.deadlineAt) throw Object.assign(new Error("QLOO_FAMILY_ACTIVE_DEADLINE"),{code:"QLOO_FAMILY_ACTIVE_DEADLINE",retryable:false});
    this.start();
    const remaining=this.deadlineAt===null?Infinity:this.deadlineAt-performance.now();
    if (remaining <= 0) {
      this.proc?.kill("SIGTERM");
      throw Object.assign(new Error("QLOO_FAMILY_ACTIVE_DEADLINE"),{code:"QLOO_FAMILY_ACTIVE_DEADLINE",retryable:false});
    }
    const familyLimited=remaining<=timeoutMs;
    const id = this.nextId++;
    const payload = JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n";
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        if (familyLimited) this.proc?.kill("SIGTERM");
        reject(Object.assign(new Error(familyLimited?"QLOO_FAMILY_ACTIVE_DEADLINE; outcome unknown, no retry":"MCP tool timeout; outcome unknown, no retry"), { code: familyLimited?"QLOO_FAMILY_ACTIVE_DEADLINE":"TOOL_TIMEOUT", retryable: false }));
      }, Math.max(1,Math.min(timeoutMs,remaining)));
      this.pending.set(id, { resolve, reject, timer });
      this.proc.stdin.write(payload);
    });
  }

  async initialize() {
    const res = await this.request("initialize", {
      protocolVersion: PINNED_REQUIREMENTS.mcpProtocolVersion,
      capabilities: {},
      clientInfo: {
        name: "cultural-launch-director",
        version: BACKEND_ADAPTER_VERSION,
      },
    });
    this.initialized = true;
    return res;
  }

  async listTools() {
    if (!this.initialized) await this.initialize();
    return this.request("tools/list", {});
  }

  async listResources() {
    if (!this.initialized) await this.initialize();
    return this.request("resources/list", {});
  }

  async readContractResource(uri = null) {
    if (!this.initialized) await this.initialize();
    let targetUri = uri;
    if (!targetUri) {
      const listRes = await this.listResources();
      targetUri = listRes?.resources?.[0]?.uri || "qloo://workflow-contract/v1";
    }
    return this.request("resources/read", { uri: targetUri });
  }

  async callTool(name, args = {}) {
    if (!this.initialized) await this.initialize();
    if (name !== "qloo_capabilities") {
      const stats = this.getPhysicalHttpStats();
      if (stats.halted || stats.attempts >= stats.limit) {
        return {
          structuredContent: {
            status: "error",
            results: [],
            warnings: [`Preflight budget gate: physical HTTP attempts (${stats.attempts}/${stats.limit}) exhausted.`],
            error: {
              code: "BUDGET_EXHAUSTED_PREFLIGHT",
              layer: "budget_guard",
              retryable: false,
              recovery: `Physical HTTP attempt limit (${stats.limit}) reached; refusing further Qloo transport calls.`,
            },
          },
          network_attempt_made: false,
        };
      }
    }
    const entry = { tool: name, arguments: structuredClone(args), requested_at: new Date().toISOString() };
    this.toolCalls.push(entry);
    try {
      const result = await this.request("tools/call", { name, arguments: args }, name === "qloo_capabilities" ? 15000 : 110000);
      entry.received_at = new Date().toISOString();
      entry.source_payload_sha256 = crypto.createHash("sha256").update(JSON.stringify(result)).digest("hex");
      entry.status = result?.structuredContent?.status || null;
      return result;
    } catch (error) { entry.error = String(error.code || "MCP_ERROR"); throw error; }
  }

  async getCapabilities() {
    return this.callTool("qloo_capabilities", {});
  }

  async describeEntity(rawQueryOrArgs) {
    const args =
      typeof rawQueryOrArgs === "string"
        ? buildCanonicalDescribeArgs(rawQueryOrArgs)
        : buildCanonicalDescribeArgs(rawQueryOrArgs?.entity || "");
    return this.callTool("qloo_describe", args);
  }

  async rankOptions({ optionType, options, signals }) {
    const args = buildCanonicalRankArgs({ optionType, options, signals });
    return this.callTool("qloo_rank", args);
  }

  async recommendMovies(seedIds) {
    return this.callTool("qloo_recommend", buildMovieRecommendArgs(seedIds));
  }

  close() {
    this.getPhysicalHttpStats();
    for (const [, { timer }] of this.pending.entries()) {
      clearTimeout(timer);
    }
    this.pending.clear();
    if (this.proc) {
      this.proc.kill("SIGTERM");
      this.proc = null;
    }
    // Counter and responses remain for settlement, including process failures.
    this.counterFilePath = null;
    this.initialized = false;
  }
}

/**
 * Performs offline-safe MCP contract discovery (`initialize` + `tools/list` + `qloo_capabilities` + `resources/read`)
 * against the installed `@qloo/qloo-harness@0.1.26` with zero network calls.
 */
export async function discoverInstalledMcpContract() {
  if (!checkQlooCliAvailable()) {
    return {
      available: false,
      error: "Installed @qloo/qloo-harness binary not found.",
    };
  }
  const session = new QlooStdioSession(null, { offlineOnly: true });
  try {
    const initRes = await session.initialize();
    const toolsRes = await session.listTools();
    const capRes = await session.getCapabilities();
    const resourceRes = await session.readContractResource();
    const physStats = session.getPhysicalHttpStats();
    const toolNames = Array.isArray(toolsRes?.tools) ? toolsRes.tools.map((t) => t.name) : [];
    const capStructured = capRes?.structuredContent || {};
    return {
      available: true,
      executable: resolveQlooMcpExecutable(),
      protocol_version: initRes?.protocolVersion || null,
      server_info: initRes?.serverInfo || null,
      tools_count: toolNames.length,
      tool_names: toolNames,
      qloo_find_present: toolNames.includes("qloo_find"),
      qloo_describe_present: toolNames.includes("qloo_describe"),
      qloo_rank_present: toolNames.includes("qloo_rank"),
      contract_version: capStructured.contract_version || null,
      contract_checksum: capStructured.contract_checksum || null,
      result_schema_version: capStructured.result_schema_version || null,
      adapter: capStructured.adapter || null,
      contract_resource_uri: resourceRes?.contents?.[0]?.uri || null,
      network_attempts: physStats.attempts,
    };
  } finally {
    session.close();
  }
}

/**
 * Invokes `cultural_launch_director.py` over JSON stdin/stdout.
 */
export function invokePythonDirector(cliFlag, payloadObj, sourceEnv = process.env) {
  const directorScript = path.join(__dirname, "cultural_launch_director.py");
  const nativeProviderEnabled = sourceEnv.DIRECTOR_ENABLE_LIVE_LLM === "1"
    && sourceEnv.DIRECTOR_LLM_PROVIDER === "guarded_qwen_18080";
  const useNativeBridge = nativeProviderEnabled && cliFlag === "--run-json"
    && payloadObj.mode === "live" && !payloadObj.cancel_requested && !payloadObj.simulated_harness_state
    && Number(payloadObj.llm_call_limit ?? 3) >= 3 && sourceEnv.DIRECTOR_PREFLIGHT_READY === "1";
  let args = ["-B", directorScript, cliFlag];
  let childEnv = Object.fromEntries(["HOME", "PATH", "LANG", "TMPDIR"]
    .filter(key => typeof sourceEnv[key] === "string").map(key => [key, sourceEnv[key]]));
  if (useNativeBridge) {
    const bridge = String(sourceEnv.DIRECTOR_QWEN_BRIDGE_ENTRY || "");
    const directorSha = String(sourceEnv.DIRECTOR_QWEN_EXPECTED_DIRECTOR_SHA256 || "");
    const runnerSha = String(sourceEnv.DIRECTOR_QWEN_EXPECTED_RUNNER_SHA256 || "");
    if (!path.isAbsolute(bridge) || !/^[a-f0-9]{64}$/.test(directorSha) || !/^[a-f0-9]{64}$/.test(runnerSha)) {
      throw new Error("Native Qwen bridge path and received source hashes must be configured by the owner.");
    }
    const activeSeconds = Math.min(Number(sourceEnv.DIRECTOR_QWEN_ACTIVE_SECONDS || "120"), Number(payloadObj.active_time_limit_ms ?? 120000) / 1000);
    if (!(activeSeconds > 0 && activeSeconds <= 120)) throw new Error("No active time remains for native roles");
    args = ["-B", bridge, "--project", __dirname, "--run-json", "--execute-authorized",
      "--expected-director-sha256", directorSha, "--expected-runner-sha256", runnerSha,
      "--active-seconds", String(activeSeconds)];
    // The Python LLM worker consumes precollected Qloo envelopes, never its credential.
    // No QLOO_* variable or credential enters this Python controller or its worker.
  } else if (nativeProviderEnabled) {
    // Fixture display and removal/export remain free of model execution.
    childEnv.DIRECTOR_ENABLE_LIVE_LLM = "0";
  }
  const child = spawnSync("python3", args, {
    input: JSON.stringify(payloadObj),
    encoding: "utf8",
    timeout: useNativeBridge ? 160000 : 30000,
    maxBuffer: 8 * 1024 * 1024,
    env: childEnv,
  });
  if (child.error) {
    throw child.error;
  }
  if (child.status !== 0) {
    throw new Error(redactText(child.stderr || `cultural_launch_director.py exited with status ${child.status}`));
  }
  return JSON.parse(child.stdout);
}


/** Read the actual HTTP warning channel: the upstream MCP harness can omit it. */
export function enrichInsightsWithPhysicalEvidence(envelope, rawEnvelope, physicalEvents, guardDirectory, requestedSignals, tool = "qloo_rank") {
  if (!["qloo_rank", "qloo_recommend"].includes(tool)) throw new Error("Unsupported insights operation");
  const label=tool==="qloo_recommend"?"recommendation":"ranking";
  const warnings=[]; const references=[];let malformedRecommendation=false;
  const returned=Array.isArray(envelope.results)?envelope.results:envelope.results?.entities || [];
  for (const event of physicalEvents.filter(e=>e.path==="/v2/insights" && e.status===200)) {
    const bytes=fs.readFileSync(path.join(guardDirectory,`http-${String(event.attempt).padStart(2,"0")}-response.txt`));
    if (crypto.createHash("sha256").update(bytes).digest("hex")!==event.redacted_response_sha256) throw new Error("PHYSICAL_PROVENANCE_MISMATCH");
    const body=JSON.parse(bytes.toString("utf8"));
    if (tool==="qloo_recommend") {
      const rows=Array.isArray(body.results)?body.results:body.results?.entities;
      if (!Array.isArray(rows) || rows.length!==returned.length || rows.some(row=>!row || typeof row!=="object" ||
          typeof (row.entity_id??row.id)!=="string" || !(row.entity_id??row.id).trim() ||
          typeof (row.affinity??row.query?.affinity)!=="number" || !Number.isFinite(row.affinity??row.query?.affinity))) malformedRecommendation=true;
    }
    if (Array.isArray(body.warnings)) warnings.push(...body.warnings);
    references.push({attempt:event.attempt,response_sha256:event.response_sha256,redacted_response_sha256:event.redacted_response_sha256});
  }
  envelope.physical_http_warnings=warnings;
  envelope.physical_http_warning_refs=references;
  const absent=new Set(warnings.flatMap(w=>w && typeof w==="object" && w.type==="not_found" && Array.isArray(w["signal.interests.entities"])?w["signal.interests.entities"]:[]));
  const absentKeys=new Set([...absent].map(id=>String(id).toLowerCase()));
  const allAbsent=requestedSignals.length>0 && requestedSignals.every(id=>absentKeys.has(String(id).toLowerCase()));
  const items=Array.isArray(envelope.results)?envelope.results:envelope.results?.entities || [];
  const measured=item=>[item.affinity,item.query?.affinity].some(v=>typeof v==="number" && Number.isFinite(v));
  if (warnings.length) {
    envelope.status=allAbsent?"empty":"degraded";
    envelope.limitations.push(allAbsent?`Qloo ${label} ignored every supplied seed. No cultural ${label} is qualified.`:`Qloo ${label} ignored or warned about part of the supplied input. No complete result is qualified.`);
    if (absent.size) {
      const signals=rawEnvelope?.structuredContent?.interpretation?.signals || [];
      const labels=[...absent].map(id=>{const item=signals.find(x=>String(x.entityId).toLowerCase()===String(id).toLowerCase());return item?.name?`${item.name} (${id})`:id;});
      envelope.limitations.push((tool==="qloo_recommend"?"Recommendation":"Ranking")+" endpoint did not recognize: "+labels.join(", ")+". Use a different public reference in a separate brief; no supplied reference was silently removed.");
    }
  }
  if (items.length && !items.every(measured) && ["ok","partial","degraded","empty"].includes(envelope.status)) {
    envelope.status=items.some(measured)?"degraded":"empty";
    envelope.limitations.push("Measured affinity is missing. Returned or input order is not a qualified cultural "+label+".");
  }
  if (malformedRecommendation) {
    envelope.status="invalid_contract";
    envelope.limitations.push("The physical recommendation response is incomplete or differs from the normalized list; no filtered subset is qualified.");
  }
  return envelope;
}

// Existing callers retain the same ranking operation and diagnostic wording.
export function enrichRankWithPhysicalEvidence(envelope, rawEnvelope, physicalEvents, guardDirectory, requestedSignals) {
  return enrichInsightsWithPhysicalEvidence(envelope,rawEnvelope,physicalEvents,guardDirectory,requestedSignals,"qloo_rank");
}

/** Owner-only execution surface. The public gateway applies a stricter input whitelist. */
export async function executeDirectorRequest(body, activeEnv = process.env, dependencies = {}) {
  const started=performance.now();
  const invoke=dependencies.invokeDirector || invokePythonDirector;
  const createSession=dependencies.sessionFactory || ((env,options)=>new QlooStdioSession(env,options));
  const fields = ["case_id", "synopsis", "suggested_public_references", "user_constraints", "confirmed_entity_ids",
    "mode", "cancel_requested", "rank_domains", "shortlist_options", "explicit_run_id", "frozen_case_sha256",
    "frozen_cases_file_sha256", "qloo_network_attempt_limit", "llm_call_limit", "active_time_limit_ms",
    "resolution_choices", "resolution_choice_provenance", "budget_profile", "allow_repair", "reference_workflow", "movie_choice"];
  let payload = Object.fromEntries(fields.filter(k => Object.hasOwn(body,k)).map(k => [k,structuredClone(body[k])]));
  payload.mode ??= "live"; payload.rank_domains ??= ["movie"];
  payload.reference_workflow ??= payload.mode==="live" && !payload.shortlist_options?"qloo_proposes":"explicit_shortlist";
  if (!["qloo_proposes","explicit_shortlist"].includes(payload.reference_workflow)) throw new Error("Unknown reference workflow");
  payload.shortlist_options ??= {};
  payload.qloo_network_attempt_limit ??= 8; payload.llm_call_limit ??= 3;
  payload.active_time_limit_ms ??= 120000;
  if (payload.mode !== "live" && payload.mode !== "fixture") throw new Error("Recorded live is a read-only evidence view, not a new run");
  const runId = payload.explicit_run_id || activeEnv.DIRECTOR_QUALIFICATION_RUN_ID || `run-${crypto.randomUUID()}`;
  if (!SAFE_RUN_ID_RE.test(runId)) throw new Error("Invalid run id");
  payload.explicit_run_id = runId;
  fs.mkdirSync(RUNS_DIR,{recursive:true,mode:0o700});
  let familyId=runId, previousMs=0, parent=null,submittedChoice=null,originalProposal=null;
  if (body.parent_run_id) {
    if (!SAFE_RUN_ID_RE.test(body.parent_run_id)) throw new Error("Invalid parent run");
    parent=loadServerOwnedBundle(body.parent_run_id);
    if (!parent || parent.workflow_status !== "needs_input") throw new Error("Parent is not an open clarification");
    const saved=JSON.parse(fs.readFileSync(path.join(RUNS_DIR,`${body.parent_run_id}-request.json`),"utf8"));
    for (const key of ["case_id","synopsis","suggested_public_references","user_constraints","rank_domains","shortlist_options"])
      if (Object.hasOwn(body,key) && JSON.stringify(body[key])!==JSON.stringify(saved[key])) throw new Error("Clarification cannot rewrite its original brief");
    const choices=parent.movie_proposal?.proposal_id?(saved.resolution_choices || {}):(payload.resolution_choices || saved.resolution_choices || {});
    if (parent.movie_proposal?.proposal_id) {
      submittedChoice=chooseMovieProposal(parent.movie_proposal,payload.movie_choice,parent.movie_proposal.input_hash);
      originalProposal=parent.movie_selection?.original_proposal || parent.movie_proposal;
    } else if (!Object.keys(choices).length) throw new Error("Explicit resolution choices required");
    const movieChoice=payload.movie_choice;
    payload={...saved,resolution_choices:choices,explicit_run_id:runId,...(movieChoice?{movie_choice:movieChoice}:{}),
      resolution_choice_provenance:{parent_run_id:body.parent_run_id,source:body.resolution_choice_provenance?.source || "explicit_gateway_submission",submitted_at:new Date().toISOString()}};
    familyId=parent.mcp_stdio_runtime.family_run_id || parent.run_id;
    previousMs=parent.mcp_stdio_runtime.active_time_used_ms || 0;
  }
  if (payload.movie_choice && !submittedChoice) throw new Error("A server-owned movie proposal is required");
  const proposeMovies=payload.reference_workflow==="qloo_proposes";
  if (proposeMovies) {payload.shortlist_options={};delete payload.insights_tool;delete payload.explicit_selected_ids;}
  let pre=invoke("--preflight-json",payload,activeEnv);
  const mayPropose=()=>proposeMovies && pre.candidate_resolution.gate_status==="ok" && pre.gate_reasons.every(reason=>reason.startsWith("explicit_same_type_shortlist_required:"));
  payload=pre.normalized_request;
  const requestPath=path.join(RUNS_DIR,`${runId}-request.json`);
  fs.writeFileSync(requestPath,JSON.stringify(payload,null,2)+"\n",{flag:"wx",mode:0o600});
  const guardDirectory=path.join(RUNS_DIR,"physical",familyId);
  if (!parent) initialiseGuardRun(guardDirectory,familyId,{maxAttempts:payload.qloo_network_attempt_limit,activeMs:payload.active_time_limit_ms});
  const before=readPhysicalCounter(guardDirectory).state;
  if (before.limit !== payload.qloo_network_attempt_limit) throw new Error("Cannot change family budget");
  const familyFile=path.join(guardDirectory,"application.json");
  if (!parent) fs.writeFileSync(familyFile,JSON.stringify({family_run_id:familyId,last_run_id:null,models_used:0,active_ms:0,inflight:null})+"\n",{flag:"wx",mode:0o600});
  const family=JSON.parse(fs.readFileSync(familyFile,"utf8"));
  if (family.family_run_id!==familyId || family.inflight || (parent && family.last_run_id!==parent.run_id)) throw new Error("Family phase already consumed or outcome unreconciled");
  if (parent && family.models_used>0) throw new Error("Native generation already consumed; explicit separately reserved correction required");
  previousMs=family.active_ms;
  if (!Number.isSafeInteger(previousMs) || previousMs<0) throw new Error("Family active time ledger invalid");
  if (previousMs+Math.ceil(performance.now()-started)>=payload.active_time_limit_ms) throw Object.assign(new Error("QLOO_FAMILY_ACTIVE_DEADLINE"),{code:"QLOO_FAMILY_ACTIVE_DEADLINE",retryable:false});
  const saveFamily=()=>{const temp=familyFile+".tmp";fs.writeFileSync(temp,JSON.stringify(family)+"\n",{mode:0o600});fs.renameSync(temp,familyFile);};
  family.inflight=runId;saveFamily();
  payload.physical_http_attempts_used=before.attempts;
  const runtime={run_id:runId,family_run_id:familyId,executed_over_stdio:false,tool_calls:[],gate_reasons:pre.gate_reasons,
    physical_http_attempts_used:before.attempts,physical_http_attempt_limit:before.limit,physical_http_events:before.events};
  let session=null,pendingProposal=null,selectionReceipt=null;
  const genreTags=[...(payload.source_genre_tags || [])];
  const stamp = (raw, entry, beforeCount) => {
    const current=session.getPhysicalHttpStats();
    const fresh=current.events.slice(beforeCount);
    const status=raw?.structuredContent?.status;
    const authenticated=fresh.length>0 && fresh.every(e=>e.status===200 && e.outcome==="response_received") && ["ok","partial","degraded","empty","needs_input"].includes(status);
    const result=normalizeHarnessEnvelope(raw,{hasServerKey:false});
    result.authentication_state=authenticated?"authenticated":(fresh.some(e=>e.status===401 || e.status===403)?"not_authenticated":"not_checked");
    Object.assign(result,{source_payload_sha256:entry.source_payload_sha256,run_id:runId,input_hash:pre.input_hash,
      requested_at:entry.requested_at,received_at:entry.received_at,network_attempt_made:fresh.length>0,
      tool_call_provenance:{tool:entry.tool,arguments:structuredClone(entry.arguments),source_payload_sha256:entry.source_payload_sha256,run_id:runId,input_hash:pre.input_hash}});
    fs.writeFileSync(path.join(guardDirectory,`mcp-${runId}-${String(session.toolCalls.length).padStart(2,"0")}.json`),JSON.stringify(raw,null,2).split(activeEnv.QLOO_API_KEY || "__NO_SECRET__").join("[REDACTED]")+"\n",{flag:"wx",mode:0o600});
    for (const event of fresh.filter(e=>e.path==="/entities"&&e.status===200)) {
      const bytes=fs.readFileSync(path.join(guardDirectory,`http-${String(event.attempt).padStart(2,"0")}-response.txt`));
      if (crypto.createHash("sha256").update(bytes).digest("hex")!==event.redacted_response_sha256) throw new Error("PHYSICAL_PROVENANCE_MISMATCH");
      const data=JSON.parse(bytes.toString("utf8")),entities=Array.isArray(data.results)?data.results:data.results?.entities || [];
      for (const entity of entities.filter(item=>item&&typeof item==="object")) for (const tag of (Array.isArray(entity.tags)?entity.tags:[]).filter(item=>item&&typeof item==="object")) {
        const urn=tag.id || tag.tag_id;
        if (typeof urn==="string"&&/^urn:tag:genre(?::|$)/.test(urn)&&typeof tag.name==="string"&&tag.name.trim()&&tag.name.length<=240)
          genreTags.push({urn,name:tag.name,seed_entity_id:entity.entity_id || entity.id,source:{tool:entry.tool,run_id:runId,requested_at:entry.requested_at,received_at:entry.received_at,response_sha256:event.response_sha256}});
      }
    }
    return ["qloo_rank","qloo_recommend"].includes(entry.tool)?enrichInsightsWithPhysicalEvidence(result,raw,fresh,guardDirectory,entry.arguments.signals || [],entry.tool):result;
  };
  try {
    if (payload.mode==="live" && (pre.allow_resolution_http || pre.allow_rank_http || mayPropose())) {
      if (!activeEnv.QLOO_API_KEY) throw new Error("QLOO_SERVER_KEY_MISSING");
      if (activeEnv.QLOO_BASE_URL!=="https://hackathon.api.qloo.com" || activeEnv.QLOO_TRUSTED_BASE_URL!==activeEnv.QLOO_BASE_URL) throw new Error("QLOO_ORIGIN_NOT_APPROVED");
      if (activeEnv.DIRECTOR_ENABLE_LIVE_LLM!=="1" || activeEnv.DIRECTOR_LLM_PROVIDER!=="guarded_qwen_18080") throw new Error("Native model route required");
      if (activeEnv.DIRECTOR_QWEN_BRIDGE_ENTRY!==path.join(__dirname,"bridge","director_entry.py")) throw new Error("Native bridge path mismatch");
      for (const [file, expected] of [["cultural_launch_director.py",activeEnv.DIRECTOR_QWEN_EXPECTED_DIRECTOR_SHA256],["guarded_qwen_runner.py",activeEnv.DIRECTOR_QWEN_EXPECTED_RUNNER_SHA256]])
        if (crypto.createHash("sha256").update(fs.readFileSync(path.join(__dirname,file))).digest("hex")!==expected) throw new Error("Source changed before transport");
      session=createSession({...activeEnv,QLOO_GUARD_DIR:guardDirectory},{attemptLimit:before.limit,
        activeTimeLimitMs:Math.max(0,payload.active_time_limit_ms-previousMs-Math.ceil(performance.now()-started))});
      const init=await session.initialize();
      const cap=await session.getCapabilities();
      if (cap?.structuredContent?.contract_checksum!==PINNED_REQUIREMENTS.contractChecksum) throw new Error("MCP_CONTRACT_DRIFT");
      Object.assign(runtime,{executed_over_stdio:true,protocol_version:init.protocolVersion,contract_version:cap.structuredContent.contract_version,contract_checksum:cap.structuredContent.contract_checksum});
      payload.precollected_describe ??= {};
      if (pre.allow_resolution_http) {
        for (const ref of payload.suggested_public_references) {
          const n=session.getPhysicalHttpStats().attempts;
          const raw=await session.describeEntity(ref);
          payload.precollected_describe[ref]=stamp(raw,session.toolCalls.at(-1),n);
          if (session.getPhysicalHttpStats().halted || ["error","invalid_contract"].includes(payload.precollected_describe[ref].status)) throw Object.assign(new Error("Qloo reference lookup failed"),{code:payload.precollected_describe[ref].error?.code || session.getPhysicalHttpStats().halted || "QLOO_DESCRIBE_ERROR"});
        }
      }
      payload.physical_http_attempts_used=session.getPhysicalHttpStats().attempts;
      pre=invoke("--preflight-json",payload,activeEnv);
      payload=pre.normalized_request;
      payload.precollected_envelopes={};
      if (mayPropose() && !session.getPhysicalHttpStats().halted) {
        const seeds=pre.candidate_resolution.confirmed_entity_ids;
        let picked=submittedChoice?[...submittedChoice.author_selected_entity_ids]:[],needsRank=false,unresolvedTitle=false;
        if (submittedChoice?.additional_reference) {
          const n=session.getPhysicalHttpStats().attempts;
          const raw=await session.describeEntity(submittedChoice.additional_reference.query+" (movie)");
          const described=stamp(raw,session.toolCalls.at(-1),n),rows=Array.isArray(described.results)?described.results:described.results?.entities || [];
          const item=rows.length===1?rows[0]:null,eid=item?.entity_id || item?.id;
          if (described.status!=="ok" || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(eid || "") || !["movie","urn:entity:movie"].includes(item?.subtype || item?.type)) unresolvedTitle=true;
          else {
            const original=parent.movie_proposal.candidates.find(c=>c.entity_id.toLowerCase()===eid.toLowerCase());
            needsRank=!original;
            if (!picked.some(id=>id.toLowerCase()===eid.toLowerCase())) picked.push(original?.entity_id || eid);
          }
        }
        if (unresolvedTitle) {
          pendingProposal=parent.movie_proposal;
          selectionReceipt={original_proposal:originalProposal,submitted_choice:payload.movie_choice,status:"needs_reference_resolution",reason:"The added title is unresolved or ambiguous. Add its director/year, or choose only proposed films."};
        } else {
          if (submittedChoice) {
            payload.shortlist_options={movie:picked};payload.explicit_selected_ids=picked;
            payload.insights_tool=needsRank?"qloo_rank":"qloo_recommend";
            pre=invoke("--preflight-json",payload,activeEnv);payload=pre.normalized_request;
          }
          const n=session.getPhysicalHttpStats().attempts;
          const raw=needsRank?await session.rankOptions({optionType:"movie",options:picked,signals:seeds}):await session.recommendMovies(seeds);
          const checked=stamp(raw,session.toolCalls.at(-1),n);
          const fresh=needsRank?null:buildMovieProposal({seedIds:seeds,inputHash:pre.input_hash,envelope:checked});
          if (!submittedChoice) pendingProposal=fresh;
          else {
            const rows=Array.isArray(checked.results)?checked.results:checked.results?.entities || [],returned=new Set(rows.map(c=>String(c.entity_id || c.id).toLowerCase()));
            const supported=checked.status==="ok" && (needsRank || fresh.status==="needs_input") && picked.every(id=>returned.has(id.toLowerCase()));
            selectionReceipt={original_proposal:originalProposal,submitted_choice:payload.movie_choice,submitted_entity_ids:picked,adopted_entity_ids:supported?picked:[],
              verification:{tool:needsRank?"qloo_rank":"qloo_recommend",run_id:runId,source_payload_sha256:checked.source_payload_sha256,candidates:needsRank?rows.map((c,i)=>({entity_id:c.entity_id || c.id,name:c.name,score_value:c.affinity??c.query?.affinity,returned_order:i})):fresh.candidates},
              status:supported?"confirmed":"stopped_without_substitution",new_rank_requested:needsRank};
            if (supported) payload.precollected_envelopes.movie=checked;
            else pendingProposal={status:checked.status==="ok"?"empty":checked.status,candidates:[],reason:"The fresh response does not support every explicit choice. Nothing was substituted or generated."};
          }
        }
      } else if (!proposeMovies && pre.allow_rank_http && !session.getPhysicalHttpStats().halted) {
        const resolvedSignals=pre.candidate_resolution.confirmed_entity_ids;
        for (const domain of payload.rank_domains) {
          const n=session.getPhysicalHttpStats().attempts;
          const raw=await session.rankOptions({optionType:domain,options:payload.shortlist_options[domain],signals:resolvedSignals});
          payload.precollected_envelopes[domain]=stamp(raw,session.toolCalls.at(-1),n);
          if (session.getPhysicalHttpStats().halted || payload.precollected_envelopes[domain].status!=="ok") break;
        }
      }
    }
  } catch(error) {
    runtime.status="error";runtime.error_code=String(error.code || error.message);
    payload.precollected_envelopes=Object.fromEntries(payload.rank_domains.map(d=>[d,{status:"error",results:[],authentication_state:"not_checked",error:{code:runtime.error_code,retryable:false},network_attempt_made:false}]));
  } finally {
    if(session) {
      runtime.tool_calls=session.toolCalls.map(x=>({...x,run_id:runId}));
      session.close();
    }
  }
  const stats=readPhysicalCounter(guardDirectory).state;
  payload.physical_http_attempts_used=stats.attempts;
  if (pendingProposal) {
    // Pending or rejected choices produce an ungenerated brief, never an empty scored selection.
    payload.shortlist_options={};payload.precollected_envelopes={};
    delete payload.insights_tool;delete payload.explicit_selected_ids;
  }
  const seeds=new Set(pre.candidate_resolution.confirmed_entity_ids.map(id=>id.toLowerCase()));
  payload.source_genre_tags=[...new Map(genreTags.filter(tag=>typeof tag.seed_entity_id==="string"&&seeds.has(tag.seed_entity_id.toLowerCase())).map(tag=>[tag.seed_entity_id.toLowerCase()+":"+tag.urn,tag])).values()].slice(0,8);
  payload.active_time_already_used_ms=Math.min(payload.active_time_limit_ms,previousMs+Math.ceil(performance.now()-started));
  pre=invoke("--preflight-json",payload,activeEnv);
  runtime.gate_reasons=pre.gate_reasons;
  const modelReady=pre.allow_model && !pendingProposal && !runtime.error_code && Object.values(payload.precollected_envelopes || {}).length>0 &&
    Object.values(payload.precollected_envelopes).every(e=>e.status==="ok" && e.authentication_state==="authenticated");
  fs.writeFileSync(requestPath,JSON.stringify(payload,null,2)+"\n",{mode:0o600});
  const bundle=invoke("--run-json",payload,{...activeEnv,DIRECTOR_PREFLIGHT_READY:modelReady?"1":"0"});
  if (pendingProposal && !runtime.error_code) {
    const pendingStatus=pendingProposal.status==="needs_input"?"needs_input":pendingProposal.status;
    bundle.workflow_status=pendingStatus;bundle.brief.qloo_api_verified=false;
    bundle.audit.pre_qloo_gate.gate_reasons=[pendingStatus==="needs_input"?"explicit_movie_choice_required":"movie_proposal_not_usable"];
    Object.assign(bundle.public_export,{status:pendingStatus,workflow_status:pendingStatus,qloo_api_verified:false,gate_reasons:bundle.audit.pre_qloo_gate.gate_reasons});
    bundle.movie_proposal=pendingProposal;bundle.public_export.movie_proposal=pendingProposal;
    for (const brief of [bundle.brief,bundle.public_export.brief]) brief.limitations=(brief.limitations || []).filter(text=>!text.startsWith("explicit_same_type_shortlist_required:")).concat(pendingProposal.reason || "Explicitly choose the films proposed by Qloo before a brief is written.");
  }
  if (selectionReceipt) {bundle.movie_selection=selectionReceipt;bundle.public_export.movie_selection=selectionReceipt;}
  bundle.public_export.genre_tags=payload.source_genre_tags;
  Object.assign(runtime,{physical_http_attempts_used:stats.attempts,physical_http_attempt_limit:stats.limit,physical_http_events:stats.events,
    active_time_used_ms:previousMs+Math.ceil(performance.now()-started),describe_calls_count:runtime.tool_calls.filter(x=>x.tool==="qloo_describe").length,
    rank_calls_count:runtime.tool_calls.filter(x=>x.tool==="qloo_rank").length,
    recommend_calls_count:runtime.tool_calls.filter(x=>x.tool==="qloo_recommend").length});
  bundle.mcp_stdio_runtime=runtime;
  if (runtime.error_code) {
    const safeError={code: String(runtime.error_code).replace(/[^a-zA-Z0-9_ -]/g, "").slice(0,100),retryable:false};
    bundle.workflow_status="error"; bundle.error=safeError;
    bundle.brief.qloo_api_verified=false;
    if (bundle.public_export) { bundle.public_export.workflow_status="error"; bundle.public_export.error=safeError; bundle.public_export.qloo_api_verified=false; }
  }
  saveServerOwnedBundle(bundle);
  family.models_used += bundle.run_budget.llm_calls_used;
  if (family.models_used>payload.llm_call_limit) throw new Error("Family native budget exceeded");
  family.active_ms=runtime.active_time_used_ms;family.last_run_id=runId;family.inflight=null;saveFamily();
  return bundle;
}

/**
 * Server-owned run bundle registry (`var/runs/<run_id>-bundle.json` + in-memory cache).
 * Reference removal operates exclusively on server-owned bundles, never trusting arbitrary client bundles.
 */
const RUNS_DIR = path.join(__dirname, "var", "runs");
const serverOwnedBundles = new Map();
const SAFE_RUN_ID_RE = /^run-[a-z0-9_-]{4,64}$/i;
const consumedQualificationRunIds = new Set();

export function saveServerOwnedBundle(bundle) {
  if (!bundle || typeof bundle !== "object" || !bundle.run_id) return null;
  const runId = String(bundle.run_id).trim();
  if (!SAFE_RUN_ID_RE.test(runId)) return null;
  fs.mkdirSync(RUNS_DIR, { recursive: true });
  const bundlePath = path.join(RUNS_DIR, `${runId}-bundle.json`);
  const copy = JSON.parse(JSON.stringify(bundle));
  serverOwnedBundles.set(runId, copy);
  fs.writeFileSync(bundlePath, JSON.stringify(copy, null, 2) + "\n", "utf8");
  return bundlePath;
}

export function loadServerOwnedBundle(runId) {
  const cleanId = String(runId || "").trim();
  if (!SAFE_RUN_ID_RE.test(cleanId)) return null;
  if (serverOwnedBundles.has(cleanId)) {
    return JSON.parse(JSON.stringify(serverOwnedBundles.get(cleanId)));
  }
  const bundlePath = path.join(RUNS_DIR, `${cleanId}-bundle.json`);
  if (fs.existsSync(bundlePath)) {
    try {
      const loaded = JSON.parse(fs.readFileSync(bundlePath, "utf8"));
      serverOwnedBundles.set(cleanId, loaded);
      return JSON.parse(JSON.stringify(loaded));
    } catch {
      return null;
    }
  }
  return null;
}

const MIME_BY_EXT = Object.freeze({
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".mp4": "video/mp4",
  ".epub": "application/epub+zip",
});

function readRequestBody(req, maxBytes = 2 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    req.on("data", (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        reject(new Error("Request body exceeds 2 MB limit"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function sendJson(res, statusCode, payload, corsOrigin = null) {
  const body = JSON.stringify(payload, null, 2) + "\n";
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    ...(corsOrigin ? { "Access-Control-Allow-Origin": corsOrigin } : {}),
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "no-store",
  });
  res.end(body);
}

/**
 * Starts the local HTTP bridge server (`http://127.0.0.1:<port>`) connecting:
 * Browser (`index.html`) -> Server (`qloo_mcp_backend.mjs`) -> Official Qloo Harness (`qloo mcp` 0.1.26) ->
 * Rank/Decision/Brief/Export (`cultural_launch_director.py`) -> Redacted proof (`var/runs/last-run-receipt.json`).
 * Supports `--port 0` (ephemeral OS-assigned port exposed on `server.effectivePort` and `server.effectiveOrigin`).
 */
export function startLocalDirectorServer({
  host = "127.0.0.1",
  port = 8787,
  allowedOrigin = process.env.DIRECTOR_ALLOWED_ORIGIN || "*",
  envOverride = null,
} = {}) {
  if (host !== "127.0.0.1") throw new Error("This isolated demo binds only to 127.0.0.1");
  const server = http.createServer(async (req, res) => {
    const activePort = server.effectivePort || port;
    const corsOrigin = `http://127.0.0.1:${activePort}`;
    let operationLock = null;
    try {
      // Enforce admission before reading a body, creating a run, spawning, or writing.
      if (req.headers.host !== `127.0.0.1:${activePort}` ||
          (req.headers.origin !== undefined && req.headers.origin !== corsOrigin)) {
        sendJson(res, 403, { status: "error", error: { code: "ORIGIN_REFUSED", retryable: false } });
        return;
      }
      if (req.method === "POST") {
        fs.mkdirSync(RUNS_DIR, { recursive: true, mode: 0o700 });
        operationLock = path.join(RUNS_DIR, "application-active.lock");
        try {
          fs.writeFileSync(operationLock, JSON.stringify({ pid: process.pid }), { flag: "wx", mode: 0o600 });
        } catch {
          operationLock = null;
          sendJson(res, 409, { status: "error", error: { code: "ONE_EXECUTION_AT_A_TIME", retryable: false } }, corsOrigin);
          return;
        }
      }
      if (req.method === "OPTIONS") {
        res.writeHead(204, {
          "Access-Control-Allow-Origin": corsOrigin,
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        });
        res.end();
        return;
      }

      // Guardrail: reject any API key sent via HTTP headers from the browser
      if (req.headers["x-api-key"] || req.headers["authorization"]) {
        sendJson(
          res,
          400,
          {
            status: "error",
            error: {
              code: "BROWSER_KEY_FORBIDDEN",
              retryable: false,
              recovery: "Never send an API key from the browser. Set QLOO_API_KEY exclusively in the server environment.",
            },
          },
          corsOrigin
        );
        return;
      }

      const urlObj = new URL(req.url || "/", `http://${host}:${activePort}`);
      const pathname = urlObj.pathname;
      const activeEnv = envOverride || process.env;

      if (req.method === "GET" && (pathname === "/api/health" || pathname === "/api/qloo-harness")) {
        const lastReceiptPath = path.join(__dirname, "var", "runs", "last-run-receipt.json");
        const contractDiscovery =
          pathname === "/api/qloo-harness" || urlObj.searchParams.get("discover") === "1"
            ? await discoverInstalledMcpContract()
            : null;
        sendJson(
          res,
          200,
          {
            status: "ok",
            adapter_version: BACKEND_ADAPTER_VERSION,
            server_url: `http://${host}:${activePort}`,
            effective_port: activePort,
            node_check: checkNodeVersion(),
            qloo_key_present_on_server: Boolean(activeEnv.QLOO_API_KEY && activeEnv.QLOO_API_KEY.trim()),
            qloo_cli_available: checkQlooCliAvailable(),
            qloo_executable: resolveQlooMcpExecutable(),
            mcp_contract_discovery: contractDiscovery,
            llm_route_configured:
              activeEnv.DIRECTOR_ENABLE_LIVE_LLM === "1"
                ? String(activeEnv.DIRECTOR_LLM_PROVIDER || "configured")
                : "offline_deterministic_template_v1_no_model_invoked",
            browser_key_accepted: false,
            pinned_requirements: PINNED_REQUIREMENTS,
            latest_receipt_exists: fs.existsSync(lastReceiptPath),
            latest_receipt_path: lastReceiptPath,
            checked_at: new Date().toISOString(),
          },
          corsOrigin
        );
        return;
      }

      if (req.method === "GET" && pathname === "/api/director/last-receipt") {
        const lastReceiptPath = path.join(__dirname, "var", "runs", "last-run-receipt.json");
        if (!fs.existsSync(lastReceiptPath)) {
          sendJson(
            res,
            404,
            {
              status: "empty",
              error: {
                code: "NO_RECEIPT_YET",
                retryable: false,
                recovery: "Trigger a run via POST /api/director/run or POST /api/qloo-harness first.",
              },
            },
            corsOrigin
          );
          return;
        }
        const doc = JSON.parse(fs.readFileSync(lastReceiptPath, "utf8"));
        sendJson(res, 200, doc, corsOrigin);
        return;
      }

      const handleServerOwnedRemoval = (body) => {
        const requestedRunId = String(body.run_id || body.bundle?.run_id || "").trim();
        const entityId = String(body.entity_id || "").trim();
        if (!requestedRunId || !entityId) {
          sendJson(
            res,
            400,
            {
              status: "error",
              error: {
                code: "MISSING_RUN_ID_OR_ENTITY_ID",
                retryable: false,
                recovery: "Provide a server-owned 'run_id' (or 'bundle.run_id') and 'entity_id' in POST /api/director/remove-reference.",
              },
            },
            corsOrigin
          );
          return;
        }
        const ownedBundle = loadServerOwnedBundle(requestedRunId);
        if (!ownedBundle) {
          sendJson(
            res,
            404,
            {
              status: "error",
              error: {
                code: "RUN_NOT_OWNED_BY_SERVER",
                retryable: false,
                recovery: `Run '${redactText(requestedRunId)}' is not owned by this server. Run /api/director/run on this server before removing a reference.`,
              },
            },
            corsOrigin
          );
          return;
        }
        const updated = invokePythonDirector("--remove-reference-json", {
          bundle: ownedBundle,
          entity_id: entityId,
        });
        if (ownedBundle.mcp_stdio_runtime) {
          updated.mcp_stdio_runtime = ownedBundle.mcp_stdio_runtime;
        }
        saveServerOwnedBundle(updated);
        sendJson(res, 200, updated, corsOrigin);
      };

      if (req.method === "POST" && (pathname === "/api/director/run" || pathname === "/api/qloo-harness")) {
        const rawBody = await readRequestBody(req);
        const body = rawBody ? JSON.parse(rawBody) : {};

        if (body.apiKey || body.qloo_api_key || body.api_key || body.token) {
          sendJson(
            res,
            400,
            {
              status: "error",
              error: {
                code: "BROWSER_KEY_FORBIDDEN",
                retryable: false,
                recovery: "Never include an API key in the browser payload. Set QLOO_API_KEY in the server environment.",
              },
            },
            corsOrigin
          );
          return;
        }

        if (body.action === "remove_reference") {
          handleServerOwnedRemoval(body);
          return;
        }

        const bundle = await executeDirectorRequest(body, activeEnv);
        saveServerOwnedBundle(bundle);
        sendJson(res, 200, bundle, corsOrigin);
        return;
      }

      if (req.method === "POST" && pathname === "/api/director/remove-reference") {
        const rawBody = await readRequestBody(req);
        const body = rawBody ? JSON.parse(rawBody) : {};
        handleServerOwnedRemoval(body);
        return;
      }

      // Static file serving for GET / and local assets in __dirname
      if (req.method === "GET") {
        const relPath = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
        const resolved = path.resolve(__dirname, relPath);
        const publicPath = ["index.html", "director-config.json"].includes(relPath) || relPath.startsWith("assets/");
        if (!publicPath || !resolved.startsWith(__dirname + path.sep) || !fs.existsSync(resolved) || fs.statSync(resolved).isDirectory()) {
          sendJson(res, 404, { status: "error", error: { code: "NOT_FOUND", path: redactText(pathname) } }, corsOrigin);
          return;
        }
        const ext = path.extname(resolved).toLowerCase();
        const contentType = MIME_BY_EXT[ext] || "application/octet-stream";
        res.writeHead(200, { "Content-Type": contentType, "Cache-Control": "no-cache" });
        fs.createReadStream(resolved).pipe(res);
        return;
      }

      sendJson(res, 405, { status: "error", error: { code: "METHOD_NOT_ALLOWED" } }, corsOrigin);
    } catch (err) {
      sendJson(
        res,
        500,
        {
          status: "error",
          error: {
            code: "INTERNAL_SERVER_ERROR",
            retryable: false,
            recovery: redactText(err?.message || String(err)),
          },
        },
        corsOrigin
      );
    } finally {
      if (operationLock) {
        try { if (JSON.parse(fs.readFileSync(operationLock, "utf8")).pid === process.pid) fs.unlinkSync(operationLock); } catch {}
      }
    }
  });

  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, () => {
      const addr = server.address();
      const effectivePort = typeof addr === "object" && addr ? addr.port : port;
      server.effectivePort = effectivePort;
      server.effectiveHost = host;
      server.effectiveOrigin = `http://${host}:${effectivePort}`;
      resolve(server);
    });
  });
}

export function isDirectCliExecution(metaUrl = import.meta.url, argv1 = process.argv[1]) {
  if (!argv1) return false;
  try {
    return fs.realpathSync(fileURLToPath(metaUrl)) === fs.realpathSync(path.resolve(argv1));
  } catch {
    try {
      return fileURLToPath(metaUrl) === path.resolve(argv1);
    } catch {
      return false;
    }
  }
}

if (isDirectCliExecution()) {
  const args = process.argv.slice(2);
  if (args.includes("--check-only")) {
    const nodeCheck = checkNodeVersion();
    discoverInstalledMcpContract()
      .then((contractDiscovery) => {
        const report = {
          adapter_version: BACKEND_ADAPTER_VERSION,
          mode: "offline_readiness_and_stdio_contract_check_no_network",
          node_check: nodeCheck,
          qloo_cli_available: checkQlooCliAvailable(),
          qloo_executable: resolveQlooMcpExecutable(),
          mcp_contract_discovery: contractDiscovery,
          pinned_requirements: PINNED_REQUIREMENTS,
          browser_key_accepted: false,
          stdio_env_keys_forwarded: Object.keys(
            buildSafeStdioEnv({ PATH: "/usr/bin", HOME: "/tmp", SECRET_TOKEN: "ignored" })
          ),
          checked_at: new Date().toISOString(),
        };
        console.log(JSON.stringify(report, null, 2));
        process.exit(nodeCheck.supported && contractDiscovery.available ? 0 : 1);
      })
      .catch((err) => {
        console.error(JSON.stringify({ event: "check_only_failed", error: redactText(err.message) }));
        process.exit(1);
      });
  } else if (args.includes("--serve")) {
    const portIdx = args.indexOf("--port");
    const hostIdx = args.indexOf("--host");
    const originIdx = args.indexOf("--origin");
    const port =
      portIdx !== -1 && args[portIdx + 1] !== undefined
        ? Number.parseInt(args[portIdx + 1], 10)
        : Number.parseInt(process.env.PORT || "8787", 10);
    const host = hostIdx !== -1 && args[hostIdx + 1] ? args[hostIdx + 1] : "127.0.0.1";
    const allowedOrigin =
      originIdx !== -1 && args[originIdx + 1]
        ? args[originIdx + 1]
        : process.env.DIRECTOR_ALLOWED_ORIGIN || "*";
    startLocalDirectorServer({ host, port, allowedOrigin })
      .then((srv) => {
        const boundPort = srv.effectivePort || port;
        console.log(
          JSON.stringify(
            {
              event: "local_director_server_listening",
              adapter_version: BACKEND_ADAPTER_VERSION,
              requested_port: port,
              effective_port: boundPort,
              url: `http://${host}:${boundPort}/`,
              api_endpoints: [
                `http://${host}:${boundPort}/api/health`,
                `http://${host}:${boundPort}/api/qloo-harness`,
                `http://${host}:${boundPort}/api/director/run`,
                `http://${host}:${boundPort}/api/director/remove-reference`,
                `http://${host}:${boundPort}/api/director/last-receipt`,
              ],
              qloo_executable: resolveQlooMcpExecutable(),
              qloo_key_present_on_server: Boolean(process.env.QLOO_API_KEY && process.env.QLOO_API_KEY.trim()),
              browser_key_accepted: false,
            },
            null,
            2
          )
        );
      })
      .catch((err) => {
        console.error(JSON.stringify({ event: "server_start_failed", error: redactText(err.message) }));
        process.exit(1);
      });
  }
}
