# Cultural Launch Director

[Open the public demo](https://yannabadie.github.io/taste-matched-trailer/) · [Devpost project](https://devpost.com/software/the-taste-matched-trailer-qloo-cultural-director-agent)

Start with the [jury guide](JURY-GUIDE.md). To request fresh evidence, use the default **Your own brief** example with **The Turn of the Screw (book)** and choose **Run a new live analysis**. New analyses use the real Qloo API. No key is entered in the browser. The original eight evaluation cases remain unchanged and expose real edge cases and coverage limits.

The separate **View recorded result** action reads one dated, authentic positive control from the operator's private local cache. It makes no new API or model call. The interface preserves the original input, provenance and export; a separate English editorial translation helps read the original French creative text. This cache needs the Mac gateway to be online, even when new live analysis is paused.

## Current workflow

The official Qloo MCP harness resolves public titles and ranks an explicit movie shortlist. The backend also reads the physical HTTP warning channel, because the harness can omit an upstream `not_found` warning. Every supplied seed must be usable for ranking, and every selected item must have a finite measured affinity. Partial coverage or missing scores stop the workflow before native generation.

When coverage is complete, a native Hermes/Qwen analyst, writer and verifier produce and check four complete creative shots. The interface displays measured scores, selected references, evidence links, timing and the received public document. Timing, framing, captions and sound are editorial choices. Music is not measured in the current profile. No audience percentage, quality gain, conversion lift or sales forecast is claimed.

## Evaluation and corrective findings

See [EVALUATION_RESULTS.json](EVALUATION_RESULTS.json) and [PHYSICAL-COVERAGE-RECEPTION.json](PHYSICAL-COVERAGE-RECEPTION.json). The earlier 2.6.1 full qualifications are withdrawn, with original outcomes preserved historically: Qloo resolves Dune and Rebecca metadata but reports their IDs as `not_found` at the ranking endpoint. C01 and C02 therefore have partial coverage. C06 has no usable ranking signal and no affinity; input order must not be presented as a measured cultural ranking.

The three incomplete-reference cases correctly make zero API/model calls. Ambiguous titles and the synthetic-title case require clarification. Version 2.6.2 was checked on the genuine archived HTTP responses, with no new inference during those regression checks. Historical response archives are retained privately, with their qualification withdrawals preserved in the public reception statistics. A separate clean-reference positive control is qualified in [PUBLIC-BROWSER-RECEPTION.json](PUBLIC-BROWSER-RECEPTION.json): 7 HTTP 200 responses, no ignored seed, 3 finite affinities, 3 native role calls, 4 complete plans and verifier acceptance. The browser download equals the server public export. This is a new custom control, not a rewritten frozen case.

## Source and architecture

Current source is in `taste-matched-trailer/`, with adjacent frozen contracts in `campagne-hackathon-2026-10-19/`. Earlier root agent files and video materials are historical. The root index and `director-config.json` serve GitHub Pages. Private credentials, runtime jobs, native receipts, raw provider payloads and machine logs are excluded.

The Python Director, official Qloo harness and existing native Hermes Studio model route run behind a private loopback backend. A separate HTTPS gateway exposes only asynchronous application jobs. POST `/api/director/run` uses an Idempotency-Key; GET `/api/director/jobs/<id>` polls the result. Explicit choices use `parent_job_id` and `resolution_choices`. Reference removal uses `{parent_job_id, entity_id}` at `/api/director/remove-reference`, then 202/poll. The gateway returns only the public export, never a private bundle. Global model settings are unchanged.

The static site does not run Python or MLX. Local reproduction requires Node 22.19+, the Qloo 0.1.26 harness, protected server credentials and the operator's qualified native Hermes/Qwen route. The private backend command is `node qloo_mcp_backend.mjs --serve --port 8787` (pass `--port 8787` as separate arguments). Its API is an internal full-bundle interface; the public frontend is connected through the gateway. No new SDK or paid model route is automatically installed.

## Availability and limits

The native backend and recorded-result cache depend on the originating Mac and its network. A dedicated user service supervises the Qloo backend, application gateway and HTTPS tunnel. The stable GitHub Pages URL reads a narrowly updated `director-config.json` pointer when the tunnel changes. User-service startup can resume after login; it does not bypass FileVault, unlock the keychain or keep a session alive after logout. No uninterrupted availability through the end of judging is guaranteed.

The gateway serves only its fixed application routes. Its two recorded-result GET routes load the expected safe export and manifest from protected local files, verify their hashes and expiry, and perform no Qloo or model work. They remain independent of live admission and backend health. A missing or invalid cache produces an explicit error. The public source contains neither the response cache nor private runtime files.

Live admission can be paused before reserving a run family, for example during Studio rendering. A guard-health response alone never proves that future compute is available. Known jobs survive a tab reload through GET-only recovery at their original gateway; an unknown submission outcome blocks duplicate submission. Dead process locks are reconciled conservatively, while an uncertain in-flight outcome is fenced rather than replayed.

The initial public pool is 10 run families, 140 physical requests and 30 native role calls, with four families per IP per hour, serial execution and no automatic refill. The change from two to four per IP preserved every existing family, reservation and consumed call. Unknown outcomes stop the service for reconciliation; a restarted process cannot reset its budget.

The [official developer guide](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide) allows private server-side caching and prohibits storing Qloo response data in a public repository. API-derived rows have therefore been removed from the current public checkout while original private receipts, counts and input cases are preserved. Old Git objects have not been rewritten; removal from the current checkout is not a claim of complete historical erasure.

## License and primary sources

MIT; preserve the repository LICENSE and rights for existing assets.

- [Qloo official hackathon kit](https://github.com/qloo/qloo-hackathon-kit)
- [Submission requirements](https://qloo.devpost.com/)
- [Official rules](https://qloo.devpost.com/rules)
