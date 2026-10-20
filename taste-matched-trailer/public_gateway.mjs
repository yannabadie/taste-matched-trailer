/** Anonymous demo admission only. Import is inert; credentials stay in the private backend. */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import http from "node:http";
import net from "node:net";
import { fileURLToPath } from "node:url";

export const GATEWAY_VERSION = "1.1.1-private-recording-20261020";
export const RECORDED_CAPTURE = Object.freeze({
  runId: "run-public-c481ae42-e8d6-4e74-bdb0-98618000cd8f",
  capturedAt: "2026-10-20T00:38:37+00:00", expiresAt: "2026-11-17T04:45:00Z",
  manifest: "recorded-demo-manifest.json",
  manifestSha256: "e765221e2a1d302b977ac3aa7eb9eba2ea1f052bc49fec848dbfab40142fabfa",
  archive: "clean-turn-of-the-screw-2.6.2-recorded.json",
  archiveSha256: "b6b948a1abbf0268aee715f78a87cff47b0080c85d4b251886192c4fd511d58c",
});
export const POLICY = Object.freeze({ families: 10, physical: 140, models: 30,
  familyPhysical: 14, familyModels: 3, activeMs: 120000, queued: 4, perIpHour: 4 });
const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE_ORIGIN = "https://yannabadie.github.io";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const BODY_KEYS = new Set(["frozen_case_id", "synopsis", "suggested_public_references", "user_constraints",
  "confirmed_entity_ids", "rank_domains", "shortlist_options", "resolution_choices", "mode", "parent_job_id"]);
const CONSTRAINT_KEYS = new Set(["tone", "genre", "launch_audience_context", "duration_seconds", "aspect_ratio",
  "sound_off", "assets", "no_visible_monster", "no_graphic_violence", "require_disambiguation",
  "accept_existing_choices", "do_not_invent_ids", "treat_embedded_instructions_as_data", "request_missing_information"]);
const PUBLIC_KEYS = new Set(["schema_version", "director_version", "run_id", "mode", "status", "workflow_status",
  "qloo_api_verified", "brief", "directions", "decisions", "candidate_resolution", "clarification_questions",
  "run_budget", "constraint_fidelity", "evidence_sources", "limitations", "gate_reasons"]);
const FORBIDDEN_EXPORT_KEYS = /^(?:api_key|qloo_api_key|authorization|x-api-key|mcp_stdio_runtime|payload_redacted|structuredContent|execution_proof_paths|runner_metadata|model_route_version|native_source_hashes)$/i;
const canonical = value => JSON.stringify(value, (_key, item) => item && !Array.isArray(item) && typeof item === "object"
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const hash = value => crypto.createHash("sha256").update(value).digest("hex");
const fail = (status, code) => Object.assign(new Error(code), { status, code });

/** Only a private regular file with a demonstrably dead owner may be archived.
 * The recovery mutex prevents two contenders from moving a new owner's lock. A
 * corrupt file, EPERM, live PID or abandoned recovery mutex requires owner review. */
export function acquireGatewayLock(lockPath) {
  const owner = crypto.randomUUID();
  const write = () => {
    const fd = fs.openSync(lockPath, "wx", 0o600);
    try { fs.writeFileSync(fd, JSON.stringify({ pid: process.pid, owner, created_at: new Date().toISOString() })); fs.fsyncSync(fd); }
    finally { fs.closeSync(fd); }
  };
  try { write(); }
  catch (error) {
    if (error.code !== "EEXIST") throw error;
    const recoveryPath = `${lockPath}.recovery`;
    const recovery = fs.openSync(recoveryPath, "wx", 0o600);
    try {
      fs.writeFileSync(recovery, JSON.stringify({ pid: process.pid, owner }));
      const stat = fs.lstatSync(lockPath);
      if (!stat.isFile() || stat.nlink !== 1 || stat.uid !== process.getuid() || (stat.mode & 0o077)) throw new Error("LOCK_OWNERSHIP_UNCERTAIN");
      const bytes = fs.readFileSync(lockPath);
      const previous = JSON.parse(bytes);
      if (!Number.isSafeInteger(previous.pid) || previous.pid < 2 || typeof previous.owner !== "string") throw new Error("LOCK_IDENTITY_UNCERTAIN");
      let dead = false;
      try { process.kill(previous.pid, 0); }
      catch (cause) { if (cause.code === "ESRCH") dead = true; else throw cause; }
      if (!dead) throw new Error("LOCK_OWNER_ALIVE");
      const current = fs.lstatSync(lockPath);
      if (current.ino !== stat.ino || current.dev !== stat.dev || !fs.readFileSync(lockPath).equals(bytes)) throw new Error("LOCK_CHANGED_DURING_RECOVERY");
      fs.renameSync(lockPath, `${lockPath}.stale-${Date.now()}-${owner}`);
      // Never overwrite a concurrent winner, and never loop back to archive it.
      write();
    } finally {
      fs.closeSync(recovery);
      try { if (JSON.parse(fs.readFileSync(recoveryPath, "utf8")).owner === owner) fs.unlinkSync(recoveryPath); } catch {}
    }
  }
  return () => { try { if (JSON.parse(fs.readFileSync(lockPath, "utf8")).owner === owner) fs.unlinkSync(lockPath); } catch {} };
}
const boundedText = (value, max) => {
  if (typeof value !== "string" || value.length > max || /\bsk-[A-Za-z0-9_-]{12,}|Authorization\s*:\s*Bearer|X-Api-Key\s*[:=]/i.test(value)) throw fail(400, "PUBLIC_INPUT_INVALID");
  return value;
};

/** Offline owner migration helpers. Neither function reads or writes runtime state. */
export function publicPolicyHash(perIpHour = POLICY.perIpHour) {
  if (![2, 4].includes(perIpHour)) throw new Error("Only the explicit2-to4 policy change is supported");
  return hash(canonical({ allowedOrigin: PAGE_ORIGIN, policy: { ...POLICY, perIpHour } }));
}

export function verifyPublicPolicyMigration(before, after) {
  if (before?.policy_hash !== publicPolicyHash(2) || after?.policy_hash !== publicPolicyHash(4)) throw new Error("Expected explicit old/new policy hashes");
  const { policy_hash: oldHash, ...oldState } = before;
  const { policy_hash: newHash, ...newState } = after;
  if (canonical(oldState) !== canonical(newState)) throw new Error("Migration may change policy_hash only; budgets, families and jobs must remain intact");
  return { old_policy_hash: oldHash, new_policy_hash: newHash, changed_fields: ["policy_hash"],
    unchanged_state_sha256: hash(canonical(oldState)), reserved_unchanged: structuredClone(before.reserved),
    families_unchanged: Object.keys(before.families || {}).length, jobs_unchanged: Object.keys(before.jobs || {}).length,
    runtime_written_by_helper: false };
}

function cleanInput(body) {
  if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).some(key => !BODY_KEYS.has(key))) throw fail(400, "PUBLIC_INPUT_FIELDS_REFUSED");
  const clean = structuredClone(body);
  if (clean.mode !== undefined && clean.mode !== "live") throw fail(400, "LIVE_DEMO_ONLY");
  if (clean.frozen_case_id !== undefined && !/^C0[1-8]$/.test(clean.frozen_case_id)) throw fail(400, "CASE_INVALID");
  if (clean.synopsis !== undefined) boundedText(clean.synopsis, 8000);
  for (const field of ["suggested_public_references", "confirmed_entity_ids"]) {
    if (clean[field] === undefined) continue;
    if (!Array.isArray(clean[field]) || clean[field].length > 3) throw fail(400, "PUBLIC_REFERENCE_LIMIT");
    for (const value of clean[field]) {
      boundedText(value, 180);
      if (field === "confirmed_entity_ids" && !UUID.test(value)) throw fail(400, "ENTITY_ID_INVALID");
    }
  }
  if (clean.rank_domains !== undefined && canonical(clean.rank_domains) !== '["movie"]') throw fail(400, "MOVIE_DOMAIN_ONLY");
  if (clean.shortlist_options !== undefined) {
    const options = clean.shortlist_options;
    if (!options || typeof options !== "object" || Array.isArray(options) || Object.keys(options).some(key => key !== "movie") ||
        !Array.isArray(options.movie) || options.movie.length < 1 || options.movie.length > 3) throw fail(400, "SHORTLIST_INVALID");
    options.movie.forEach(value => { if (!boundedText(value, 180).trim()) throw fail(400, "SHORTLIST_INVALID"); });
  }
  if (clean.resolution_choices !== undefined) {
    const choices = clean.resolution_choices;
    if (!choices || typeof choices !== "object" || Array.isArray(choices) || Object.keys(choices).length > 3) throw fail(400, "CHOICES_INVALID");
    for (const [query, selected] of Object.entries(choices)) {
      boundedText(query, 180);
      if (typeof selected !== "string" || !UUID.test(selected)) throw fail(400, "CHOICES_INVALID");
    }
    if (!clean.parent_job_id && Object.keys(choices).length) throw fail(400, "CHOICE_PARENT_REQUIRED");
  }
  if (clean.parent_job_id !== undefined && !UUID.test(clean.parent_job_id)) throw fail(400, "PARENT_JOB_INVALID");
  if (clean.user_constraints !== undefined) {
    const constraints = clean.user_constraints;
    if (!constraints || typeof constraints !== "object" || Array.isArray(constraints)) throw fail(400, "CONSTRAINTS_INVALID");
    for (const [key, value] of Object.entries(constraints)) {
      if (!CONSTRAINT_KEYS.has(key)) throw fail(400, "CONSTRAINT_FIELD_REFUSED");
      if (["tone", "genre", "launch_audience_context"].includes(key)) boundedText(value, 240);
      else if (key === "duration_seconds") {
        if (!Number.isInteger(value) || value < 1 || value > 120) throw fail(400, "DURATION_INVALID");
      } else if (key === "aspect_ratio") {
        if (!["9:16", "16:9", "1:1"].includes(value)) throw fail(400, "ASPECT_INVALID");
      } else if (key === "assets") {
        if (!Array.isArray(value) || value.length > 6 || value.some(asset => typeof asset !== "string" || asset.length > 40)) throw fail(400, "ASSETS_INVALID");
      } else if (typeof value !== "boolean") throw fail(400, "CONSTRAINT_TYPE_INVALID");
    }
  }
  return clean;
}

function publicProjection(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw fail(502, "PUBLIC_EXPORT_MISSING");
  const scrub = value => {
    if (Array.isArray(value)) return value.map(scrub);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value)
      .filter(([key]) => !FORBIDDEN_EXPORT_KEYS.test(key)).map(([key, item]) => [key, scrub(item)]));
    if (typeof value === "string" && /(?:\/Users\/|\/home\/|\/var\/|\/tmp\/|file:\/\/|\bsk-[A-Za-z0-9_-]{12,}|Authorization\s*:\s*Bearer)/i.test(value)) return "[private detail omitted]";
    return value;
  };
  const projected = scrub(Object.fromEntries(Object.entries(raw).filter(([key]) => PUBLIC_KEYS.has(key))));
  if (!projected.brief || !projected.candidate_resolution || !Array.isArray(projected.decisions) || !projected.run_id || projected.mode !== "live") throw fail(502, "PUBLIC_EXPORT_INVALID");
  if (Buffer.byteLength(JSON.stringify(projected)) > 512 * 1024) throw fail(502, "PUBLIC_EXPORT_TOO_LARGE");
  return projected;
}

/** Two pinned files only. No filenames/paths are ever taken from an HTTP request. */
function readRecordedPair(directory, now) {
  if (now() >= Date.parse(RECORDED_CAPTURE.expiresAt)) throw fail(410, "RECORDED_CAPTURE_EXPIRED");
  if (!directory) throw fail(503, "RECORDED_CAPTURE_UNAVAILABLE");
  try {
    const folder = fs.lstatSync(directory);
    if (!folder.isDirectory() || folder.uid !== process.getuid() || (folder.mode & 0o077)) throw new Error("PRIVATE_DIRECTORY_REQUIRED");
    const load = (name, expected) => {
      const file = path.join(directory, name);
      const stat = fs.lstatSync(file);
      if (!stat.isFile() || stat.nlink !== 1 || stat.uid !== process.getuid() || (stat.mode & 0o077) || stat.size > 131072) throw new Error("PRIVATE_FILE_REQUIRED");
      const bytes = fs.readFileSync(file);
      if (hash(bytes) !== expected) throw new Error("CAPTURE_HASH_MISMATCH");
      return { bytes, document: JSON.parse(bytes.toString("utf8")) };
    };
    const manifest = load(RECORDED_CAPTURE.manifest, RECORDED_CAPTURE.manifestSha256);
    const archive = load(RECORDED_CAPTURE.archive, RECORDED_CAPTURE.archiveSha256);
    const info = manifest.document;
    const saved = archive.document;
    if (info.original_run_id !== RECORDED_CAPTURE.runId || info.kind !== "single_recorded_demonstration" ||
        info.display_mode !== "recorded_live" || info.captured_at !== RECORDED_CAPTURE.capturedAt ||
        info.archive?.sha256 !== RECORDED_CAPTURE.archiveSha256 || info.archive?.file !== RECORDED_CAPTURE.archive ||
        info.archive?.bytes !== archive.bytes.length || saved.kind !== "recorded_export_of_clean_positive_control" ||
        saved.not_a_new_live_request !== true || saved.captured_at !== RECORDED_CAPTURE.capturedAt ||
        saved.document?.run_id !== RECORDED_CAPTURE.runId || canonical(publicProjection(saved.document)) !== canonical(saved.document)) throw new Error("CAPTURE_PROVENANCE_INVALID");
    if (Date.parse(RECORDED_CAPTURE.capturedAt) > now()) throw new Error("CAPTURE_DATE_IN_FUTURE");
    return { manifest: manifest.bytes, archive: archive.bytes };
  } catch { throw fail(503, "RECORDED_CAPTURE_UNAVAILABLE_OR_INVALID"); }
}

/** No listener is opened here. Tests inject internalPost; production only calls a loopback backend. */
export function createPublicGateway({ allowedOrigin, backendOrigin, stateDirectory, trustedProxy = null,
    now = Date.now, internalPost = null, internalReady = null, admissionFile = null, recordedDirectory = null, autoStart = true } = {}) {
  if (allowedOrigin !== PAGE_ORIGIN) throw new Error("Exact received Pages origin required");
  const endpoint = new URL(backendOrigin || "invalid:");
  if (endpoint.protocol !== "http:" || endpoint.hostname !== "127.0.0.1" || endpoint.username || endpoint.password || endpoint.pathname !== "/" || endpoint.search || endpoint.hash) throw new Error("Loopback backend origin required");
  if (!path.isAbsolute(stateDirectory || "")) throw new Error("Private absolute state directory required");
  if (trustedProxy !== null && !["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(trustedProxy)) throw new Error("Only an explicitly trusted loopback proxy is supported");
  if (admissionFile !== null && !path.isAbsolute(admissionFile)) throw new Error("Absolute private admission file required");
  if (recordedDirectory !== null && !path.isAbsolute(recordedDirectory)) throw new Error("Absolute private recording directory required");
  fs.mkdirSync(stateDirectory, { recursive: true, mode: 0o700 });
  const lockPath = path.join(stateDirectory, "gateway.lock");
  const statePath = path.join(stateDirectory, "jobs.json");
  const owner = crypto.randomUUID();
  const release = acquireGatewayLock(lockPath);
  const policyHash = publicPolicyHash();
  let state;
  try {
    state = fs.existsSync(statePath) ? JSON.parse(fs.readFileSync(statePath, "utf8")) : {
      schema_version: 1, policy_hash: policyHash, created_at: new Date(now()).toISOString(), ip_salt: crypto.randomBytes(24).toString("hex"),
      reserved: { families: 0, physical: 0, models: 0 }, families: {}, jobs: {}, idempotency: {}, halted: null,
    };
    if (state.schema_version !== 1 || state.policy_hash !== policyHash || typeof state.ip_salt !== "string" || !state.jobs || !state.idempotency || !state.families ||
        !Number.isInteger(state.reserved?.families) || state.reserved.families < 0 || state.reserved.families > POLICY.families ||
        state.reserved.physical !== state.reserved.families * POLICY.familyPhysical || state.reserved.models !== state.reserved.families * POLICY.familyModels ||
        Object.keys(state.families).length !== state.reserved.families) throw new Error("Persistent public budget/state invalid; no reset");
  } catch (error) { release(); throw error; }
  const persist = () => {
    const temporary = `${statePath}.${owner}.tmp`;
    const fd = fs.openSync(temporary, "w", 0o600);
    try { fs.writeFileSync(fd, JSON.stringify(state)); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    fs.renameSync(temporary, statePath);
  };
  for (const job of Object.values(state.jobs)) {
    if (job.status === "running") {
      job.status = "failed"; job.error = { code: "OUTCOME_UNKNOWN", message: "Previous execution requires reconciliation; no automatic retry." };
      state.halted = "RESTART_WITH_UNKNOWN_OUTCOME";
    }
  }
  persist();
  process.on("exit", release);
  const peerHash = ip => crypto.createHmac("sha256", state.ip_salt).update(ip).digest("hex");
  const reply = job => ({ job_id: job.id, status: job.status, poll_url: `/api/director/jobs/${job.id}`,
    ...(job.original_case_id ? { original_case_id: job.original_case_id, provenance: { kind: job.provenance_kind, parent_job_id: job.parent_job_id, frozen_case_completed: false } } : {}),
    ...(job.public_result ? { bundle: structuredClone(job.public_result) } : {}), ...(job.error ? { error: job.error } : {}) });
  const post = internalPost || (async (route, body) => {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 290000);
    try {
      const response = await fetch(new URL(route, endpoint), { method: "POST", redirect: "error", signal: abort.signal,
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const text = await response.text();
      if (Buffer.byteLength(text) > 3 * 1024 * 1024 || !response.ok) throw fail(502, "BACKEND_FAILED_OR_UNKNOWN");
      return JSON.parse(text);
    } finally { clearTimeout(timeout); }
  });
  const admissionOpen = () => {
    if (!admissionFile) return true;
    try {
      const lease = JSON.parse(fs.readFileSync(admissionFile, "utf8"));
      return lease.schema_version === 1 && lease.accepting === true && Number.isFinite(Date.parse(lease.expires_at)) && Date.parse(lease.expires_at) > now();
    } catch { return false; }
  };
  const backendReady = internalReady || (internalPost ? async () => true : async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    try {
      const response = await fetch(new URL("/api/health", endpoint), { redirect: "error", signal: controller.signal });
      const text = await response.text();
      if (!response.ok || Buffer.byteLength(text) > 65536) return false;
      const health = JSON.parse(text);
      return health.status === "ok" && health.qloo_key_present_on_server === true && health.llm_route_configured === "guarded_qwen_18080";
    } catch { return false; }
    finally { clearTimeout(timeout); }
  });
  let pumping = false;
  let pumpPromise = Promise.resolve();
  let closed = false;
  const pump = () => {
    if (pumping || closed || state.halted) return pumpPromise;
    pumping = true;
    pumpPromise = (async () => {
      try {
        for (;;) {
          if (closed || state.halted) break;
          const job = Object.values(state.jobs).find(value => value.status === "queued");
          if (!job) break;
          if (!admissionOpen() || !await backendReady() || !admissionOpen()) {
            job.status = "failed";
            job.error = { code: "BACKEND_UNAVAILABLE_BEFORE_DISPATCH", message: "The backend is unavailable. No execution was dispatched; no automatic retry." };
            job.finished_at = new Date(now()).toISOString();
            if (job.family_id) state.families[job.family_id].pending_job = null;
            persist(); continue;
          }
          job.status = "running"; job.dispatched_at = new Date(now()).toISOString(); persist();
          try {
            const raw = await post(job.route, job.request);
            const projected = publicProjection(raw.public_export);
            if (raw.run_id !== job.run_id || projected.run_id !== raw.run_id || projected.workflow_status !== raw.workflow_status || projected.qloo_api_verified !== raw.brief?.qloo_api_verified) throw fail(502, "BACKEND_IDENTITY_INVALID");
            const budget = raw.run_budget || {};
            if (job.family_id) {
              const family = state.families[job.family_id];
              if (!Number.isInteger(budget.qloo_network_attempts_used) || !Number.isInteger(budget.llm_calls_used) ||
                  budget.qloo_network_attempts_used < family.physical_used || budget.llm_calls_used < family.models_used ||
                  budget.qloo_network_attempts_used > POLICY.familyPhysical || budget.llm_calls_used > POLICY.familyModels) throw fail(502, "FAMILY_COUNTER_INVALID");
              family.physical_used = budget.qloo_network_attempts_used; family.models_used = budget.llm_calls_used;
              family.last_job = job.id;
              family.pending_job = null;
              family.completed = raw.workflow_status === "ok" && projected.qloo_api_verified === true;
            } else if (budget.qloo_network_attempts_used !== 0 || budget.llm_calls_used !== 0 || projected.qloo_api_verified === true) throw fail(502, "ZERO_BUDGET_GATE_VIOLATION");
            if (job.original_case_id) {
              projected.brief.original_case_id = job.original_case_id;
              projected.brief.provenance = { kind: job.provenance_kind, parent_job_id: job.parent_job_id, frozen_case_completed: false };
              projected.limitations = [...(projected.limitations || []), `Custom request derived from ${job.original_case_id}; the original frozen case is not completed. Parent job: ${job.parent_job_id || "none"}.`];
            }
            job.public_result = projected;
            job.status = raw.workflow_status === "needs_input" ? "needs_input"
              : raw.workflow_status === "ok" && projected.qloo_api_verified === true ? "completed" : "failed";
            if (job.status === "failed") job.error = { code: "RUN_NOT_COMPLETED", message: "The result did not complete; there is no automatic retry." };
          } catch {
            job.status = "failed";
            job.error = { code: "OUTCOME_UNKNOWN", message: "The execution needs reconciliation; there is no automatic retry." };
            state.halted = "BACKEND_OUTCOME_UNKNOWN";
          }
          job.finished_at = new Date(now()).toISOString(); persist();
        }
      } finally { pumping = false; }
    })();
    return pumpPromise;
  };

  const submit = (body, { origin, ip, idempotencyKey, removal = false } = {}) => {
    if (origin !== allowedOrigin) throw fail(403, "ORIGIN_REFUSED");
    if (!net.isIP(ip || "")) throw fail(400, "CLIENT_ADDRESS_INVALID");
    if (typeof idempotencyKey !== "string" || !/^[A-Za-z0-9._:-]{16,128}$/.test(idempotencyKey)) throw fail(400, "IDEMPOTENCY_KEY_REQUIRED");
    let clean;
    if (removal) {
      if (!body || Object.keys(body).some(key => !["parent_job_id", "entity_id"].includes(key)) || !UUID.test(body.parent_job_id || "") || !UUID.test(body.entity_id || "")) throw fail(400, "REMOVAL_INVALID");
      clean = structuredClone(body);
    } else clean = cleanInput(body);
    const ownerIp = peerHash(ip);
    const keyHash = hash(idempotencyKey);
    const requestHash = hash(canonical({ route: removal ? "remove" : "run", body: clean }));
    const previous = state.idempotency[keyHash];
    if (previous) {
      if (previous.request_hash !== requestHash || previous.owner_ip !== ownerIp) throw fail(409, "IDEMPOTENCY_CONFLICT");
      return reply(state.jobs[previous.job_id]);
    }
    if (closed || state.halted) throw fail(503, "DEMO_RECONCILIATION_REQUIRED");
    if (Object.values(state.jobs).filter(job => job.status === "queued").length >= POLICY.queued) throw fail(429, "QUEUE_FULL");
    if (Object.keys(state.jobs).length >= 256) throw fail(429, "DEMO_JOB_STORAGE_FULL");
    const parent = clean.parent_job_id ? state.jobs[clean.parent_job_id] : null;
    if (clean.parent_job_id && (!parent || parent.owner_ip !== ownerIp || !["completed", "needs_input"].includes(parent.status))) throw fail(409, "PARENT_JOB_NOT_AVAILABLE");
    if (parent?.family_id) {
      const family = state.families[parent.family_id];
      if (family.pending_job) throw fail(409, "FAMILY_OPERATION_PENDING");
      if (family.last_job !== parent.id) throw fail(409, "STALE_PARENT_JOB");
      if (!removal && (parent.status !== "needs_input" || family.models_used >= POLICY.familyModels)) throw fail(409, "FAMILY_ANALYSIS_BUDGET_CLOSED");
    }
    if (removal) {
      const ids = new Set();
      const collect = value => {
        if (typeof value === "string" && UUID.test(value)) ids.add(value);
        else if (Array.isArray(value)) value.forEach(collect);
        else if (value && typeof value === "object") Object.values(value).forEach(collect);
      };
      collect(parent.public_result);
      if (!ids.has(clean.entity_id)) throw fail(400, "REFERENCE_NOT_IN_PARENT_RESULT");
    }
    let request;
    let originalCaseId = null;
    let provenanceKind = null;
    if (removal) request = { run_id: parent.run_id, entity_id: clean.entity_id };
    else {
      let frozen = null;
      let frozenFileHash = null;
      const frozenCaseId = clean.frozen_case_id || parent?.input?.case_id;
      if (frozenCaseId) {
        const bytes = fs.readFileSync(path.join(HERE, "..", "campagne-hackathon-2026-10-19", "validation", "CAS-EVALUATION.json"));
        const file = JSON.parse(bytes);
        frozenFileHash = hash(bytes);
        frozen = file.cases.find(value => value.id === frozenCaseId);
      }
      request = { ...(parent?.input || {}), ...(frozen ? { synopsis: frozen.brief, suggested_public_references: frozen.suggested_public_references, user_constraints: frozen.user_constraints } : {}), ...clean };
      delete request.parent_job_id;
      delete request.frozen_case_id;
      if (frozen) {
        const original = { synopsis: frozen.brief, suggested_public_references: frozen.suggested_public_references, user_constraints: frozen.user_constraints };
        const effective = { synopsis: request.synopsis, suggested_public_references: request.suggested_public_references, user_constraints: request.user_constraints };
        if (canonical(original) === canonical(effective)) {
          request.case_id = frozen.id;
          request.frozen_case_sha256 = hash(canonical(frozen));
          request.frozen_cases_file_sha256 = frozenFileHash;
        } else {
          originalCaseId = frozen.id; provenanceKind = "custom_from_frozen_case";
          delete request.case_id; delete request.frozen_case_sha256; delete request.frozen_cases_file_sha256;
        }
      }
      request.mode = "live"; request.rank_domains = ["movie"]; request.allow_repair = false;
      if (Object.keys(request.resolution_choices || {}).length) {
        const groups = parent?.public_result?.candidate_resolution?.resolved_groups || [];
        for (const [query, selected] of Object.entries(request.resolution_choices)) {
          const group = groups.find(item => item.query === query);
          if (!group || !(group.candidates || []).some(candidate => (candidate.entity_id || candidate.id) === selected)) throw fail(400, "CHOICE_NOT_IN_PARENT_RESPONSE");
        }
      }
    }
    let familyId = parent?.family_id || null;
    const usableRefs = !removal && Array.isArray(request.suggested_public_references) && request.suggested_public_references.some(value => value.trim());
    const newFamily = !removal && !familyId && usableRefs;
    const id = crypto.randomUUID();
    const runId = removal ? parent.run_id : `run-public-${crypto.randomUUID()}`;
    if (newFamily) {
      if (state.reserved.families >= POLICY.families || state.reserved.physical + POLICY.familyPhysical > POLICY.physical || state.reserved.models + POLICY.familyModels > POLICY.models) throw fail(429, "DEMO_BUDGET_EXHAUSTED");
      const recent = Object.values(state.families).filter(family => family.owner_ip === ownerIp && family.reserved_at_ms > now() - 3600000).length;
      if (recent >= POLICY.perIpHour) throw fail(429, "FAMILY_RATE_LIMIT");
      familyId = runId;
      state.families[familyId] = { root_run_id: runId, owner_ip: ownerIp, reserved_at_ms: now(), reserved_before_dispatch: true,
        physical_cap: POLICY.familyPhysical, models_cap: POLICY.familyModels, physical_used: 0, models_used: 0, completed: false };
      state.reserved.families++; state.reserved.physical += POLICY.familyPhysical; state.reserved.models += POLICY.familyModels;
    }
    const publicInput = removal ? structuredClone(parent.input) : structuredClone(request);
    if (!removal) {
      request.explicit_run_id = runId;
      request.qloo_network_attempt_limit = familyId ? POLICY.familyPhysical : 0;
      request.llm_call_limit = familyId ? POLICY.familyModels : 0;
      request.active_time_limit_ms = POLICY.activeMs;
      if (parent?.family_id) request.parent_run_id = parent.run_id;
      if (newFamily && parent && !parent.family_id) {
        originalCaseId = parent.original_case_id || parent.input.case_id || null;
        provenanceKind = "custom_after_zero_cost_clarification";
        for (const field of ["case_id", "frozen_case_sha256", "frozen_cases_file_sha256"]) { delete request[field]; delete publicInput[field]; }
      }
    }
    const job = { id, run_id: runId, family_id: familyId, parent_job_id: parent?.id || null, original_case_id: originalCaseId, provenance_kind: provenanceKind,
      owner_ip: ownerIp, status: "queued", created_at: new Date(now()).toISOString(),
      route: removal ? "/api/director/remove-reference" : "/api/director/run", request, input: publicInput };
    if (familyId) state.families[familyId].pending_job = id;
    state.jobs[id] = job;
    state.idempotency[keyHash] = { job_id: id, request_hash: requestHash, owner_ip: ownerIp };
    persist(); // Includes the complete irreversible family reservation before internal POST.
    if (autoStart) queueMicrotask(pump);
    return reply(job);
  };

  // Readiness is tested before irreversible admission, and again before POST.
  // A failed check never allocates a family or changes the global unknown fence.
  const admit = async (body, context) => {
    if (context?.origin !== allowedOrigin) throw fail(403, "ORIGIN_REFUSED");
    if (!admissionOpen() || !await backendReady() || !admissionOpen()) throw fail(503, "DEMO_TEMPORARILY_UNAVAILABLE");
    return submit(body, context);
  };

  const handle = async (req, res) => {
    const origin = req.headers.origin;
    const send = (code, value) => {
      res.writeHead(code, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
        ...(origin === allowedOrigin ? { "Access-Control-Allow-Origin": allowedOrigin, "Vary": "Origin" } : {}) });
      res.end(JSON.stringify(value));
    };
    try {
      const route = new URL(req.url || "/", "http://gateway.invalid").pathname;
      if (req.method === "GET" && route === "/api/health" && (origin === undefined || origin === allowedOrigin)) {
        send(200, { status: "ok", gateway_version: GATEWAY_VERSION, admission_open: admissionOpen() && !state.halted && !closed,
          reconciliation_required: Boolean(state.halted), running: Object.values(state.jobs).filter(job => job.status === "running").length,
          remaining_families: POLICY.families - state.reserved.families, qloo_calls_on_health: 0, model_calls_on_health: 0,
          end_to_end_verified_by_health: false }); return;
      }
      if (origin !== allowedOrigin) throw fail(403, "ORIGIN_REFUSED");
      if (req.method === "OPTIONS") {
        res.writeHead(204, { "Access-Control-Allow-Origin": allowedOrigin, "Vary": "Origin",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type, Idempotency-Key" }); res.end(); return;
      }
      if (req.method === "GET" && ["/api/director/recorded/manifest", "/api/director/recorded/archive"].includes(route)) {
        const pair = readRecordedPair(recordedDirectory, now);
        const bytes = route.endsWith("/manifest") ? pair.manifest : pair.archive;
        res.writeHead(200, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff", "Access-Control-Allow-Origin": allowedOrigin, "Vary": "Origin",
          "X-Recorded-Captured-At": RECORDED_CAPTURE.capturedAt, "X-Recorded-Expires-At": RECORDED_CAPTURE.expiresAt });
        res.end(bytes); return;
      }
      const match = route.match(/^\/api\/(?:director\/jobs|jobs)\/([0-9a-f-]{36})$/i);
      if (req.method === "GET" && match) {
        const job = state.jobs[match[1]];
        if (!job) throw fail(404, "JOB_NOT_FOUND");
        send(200, reply(job)); return;
      }
      if (req.method !== "POST" || !["/api/director/run", "/api/jobs", "/api/director/remove-reference"].includes(route)) throw fail(404, "ROUTE_NOT_FOUND");
      if (req.headers["authorization"] || req.headers["x-api-key"]) throw fail(400, "CLIENT_CREDENTIAL_FORBIDDEN");
      if (!String(req.headers["content-type"] || "").toLowerCase().startsWith("application/json")) throw fail(415, "JSON_REQUIRED");
      const chunks = []; let size = 0;
      for await (const chunk of req) {
        size += chunk.length;
        if (size > 16384) throw fail(413, "REQUEST_TOO_LARGE");
        chunks.push(chunk);
      }
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      const peer = req.socket.remoteAddress;
      const forwarded = req.headers["cf-connecting-ip"];
      const ip = trustedProxy && peer === trustedProxy && typeof forwarded === "string" && net.isIP(forwarded) ? forwarded : peer;
      send(202, await admit(body, { origin, ip, idempotencyKey: req.headers["idempotency-key"], removal: route.endsWith("remove-reference") }));
    } catch (error) { send(error.status || 400, { error: { code: error.code || "INVALID_PUBLIC_REQUEST", message: "Request refused; no automatic retry." } }); }
  };
  if (autoStart && !state.halted) queueMicrotask(pump);
  return { handle, submit, admit, pump, getJob: id => state.jobs[id] ? reply(state.jobs[id]) : null,
    close: async () => { closed = true; await pumpPromise; process.removeListener("exit", release); release(); } };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!process.argv.includes("--serve")) throw new Error("Use --serve only after private source and budget approval");
  if (Object.hasOwn(process.env, "QLOO_API_KEY")) throw new Error("Gateway must run without a Qloo credential");
  const gateway = createPublicGateway({ allowedOrigin: process.env.DIRECTOR_PUBLIC_ALLOWED_ORIGIN,
    backendOrigin: process.env.DIRECTOR_PUBLIC_BACKEND_ORIGIN, stateDirectory: process.env.DIRECTOR_PUBLIC_STATE_DIR,
    trustedProxy: process.env.DIRECTOR_PUBLIC_TRUST_PROXY || null,
    admissionFile: process.env.DIRECTOR_PUBLIC_ADMISSION_FILE || null,
    recordedDirectory: process.env.DIRECTOR_PUBLIC_RECORDED_DIR || path.resolve(process.env.DIRECTOR_PUBLIC_STATE_DIR, "../../jury-runtime-20261020/recorded-c481") });
  const server = http.createServer(gateway.handle);
  const port = Number(process.env.DIRECTOR_PUBLIC_PORT || 0);
  server.listen(port, "127.0.0.1", () => process.stdout.write(JSON.stringify({ event: "public_gateway_ready", version: GATEWAY_VERSION, port: server.address().port }) + "\n"));
  process.once("SIGTERM", async () => { server.close(); await gateway.close(); process.exit(0); });
}
