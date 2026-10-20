# Cultural Launch Director

[Open the public demo](https://yannabadie.github.io/taste-matched-trailer/) · [Devpost project](https://devpost.com/software/the-taste-matched-trailer-qloo-cultural-director-agent)

Use the default **Your own brief** example with **The Turn of the Screw (book)** and choose **Create the brief**. Public requests use the real Qloo API. No key is entered in the browser. The original eight evaluation cases remain unchanged and expose real edge cases and coverage limits.

## Current workflow

The official Qloo MCP harness resolves public titles and ranks an explicit movie shortlist. The backend also reads the physical HTTP warning channel, because the harness can omit an upstream `not_found` warning. Every supplied seed must be usable for ranking, and every selected item must have a finite measured affinity. Partial coverage or missing scores stop the workflow before native generation.

When coverage is complete, a native Hermes/Qwen analyst, writer and verifier produce and check four complete creative shots. The interface displays measured scores, selected references, evidence links, timing and the received public document. Timing, framing, captions and sound are editorial choices. Music is not measured in the current profile. No audience percentage, quality gain, conversion lift or sales forecast is claimed.

## Evaluation and corrective findings

See [EVALUATION_RESULTS.json](EVALUATION_RESULTS.json) and [PHYSICAL-COVERAGE-RECEPTION.json](PHYSICAL-COVERAGE-RECEPTION.json). The earlier 2.6.1 full qualifications are withdrawn, with original outcomes preserved historically: Qloo resolves Dune and Rebecca metadata but reports their IDs as `not_found` at the ranking endpoint. C01 and C02 therefore have partial coverage. C06 has no usable ranking signal and no affinity; input order must not be presented as a measured cultural ranking.

The three incomplete-reference cases correctly make zero API/model calls. Ambiguous titles and the synthetic-title case require clarification. Version 2.6.2 was checked on the genuine archived HTTP responses, with no new inference during those regression checks. Historical artifacts under `evidence/` are expressly unqualified, not LIVE fallbacks. A separate clean-reference positive control is now qualified in [PUBLIC-BROWSER-RECEPTION.json](PUBLIC-BROWSER-RECEPTION.json): 7 HTTP 200 responses, no ignored seed, 3 finite affinities, 3 native role calls, 4 complete plans and verifier acceptance. The browser download equals the server public export. This is a new custom control, not a rewritten frozen case.

## Source and architecture

Current source is in `taste-matched-trailer/`, with adjacent frozen contracts in `campagne-hackathon-2026-10-19/`. Earlier root agent files and video materials are historical. The root index and `director-config.json` serve GitHub Pages. Private credentials, runtime jobs, native receipts, raw provider payloads and machine logs are excluded.

The Python Director, official Qloo harness and existing native Hermes Studio model route run behind a private loopback backend. A separate HTTPS gateway exposes only asynchronous application jobs. POST `/api/director/run` uses an Idempotency-Key; GET `/api/director/jobs/<id>` polls the result. Explicit choices use `parent_job_id` and `resolution_choices`. Reference removal uses `{parent_job_id, entity_id}` at `/api/director/remove-reference`, then 202/poll. The gateway returns only the public export, never a private bundle. Global model settings are unchanged.

The static site does not run Python or MLX. Local reproduction requires Node 22.19+, the Qloo 0.1.26 harness, protected server credentials and the operator's qualified native Hermes/Qwen route. The private backend command is `node qloo_mcp_backend.mjs --serve --port 8787` (pass `--port 8787` as separate arguments). Its API is an internal full-bundle interface; the public frontend is connected through the gateway. No new SDK or paid model route is automatically installed.

## Availability and limits

The live backend depends on the originating Mac and the temporary HTTPS tunnel remaining online. There is no reboot autostart or guaranteed availability through the 17 November 2026, 05:45 Paris end of judging. The stable GitHub Pages URL remains even if the temporary tunnel stops. Application-only routing keeps the native model guard and private files inaccessible.

The initial public pool is 10 run families, 140 physical requests and 30 native role calls, with four families per IP per hour, serial execution and no automatic refill. The change from two to four per IP preserved every existing family, reservation and consumed call. Unknown outcomes stop the service for reconciliation; a restarted process cannot reset its budget.

## License and primary sources

MIT; preserve the repository LICENSE and rights for existing assets.

- [Qloo official hackathon kit](https://github.com/qloo/qloo-hackathon-kit)
- [Submission requirements](https://qloo.devpost.com/)
- [Official rules](https://qloo.devpost.com/rules)
