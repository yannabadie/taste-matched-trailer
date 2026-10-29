# Cultural Launch Director

[Open the public demo](https://yannabadie.github.io/taste-matched-trailer/) · [Devpost project](https://devpost.com/software/the-taste-matched-trailer-qloo-cultural-director-agent)

Start with the [29 October recorded result](https://yannabadie.github.io/taste-matched-trailer/qloo-proposed-recording.html): six films proposed by Qloo, two retained after explicit confirmation, and four written shots. It includes an attributed English reading aid beside the unchanged French original and its editorial reservations. Reading it makes no new API or model call. The [jury guide](JURY-GUIDE.md) separates this case from the older recording.

To request fresh evidence, use the default **Your own brief** example with **The Turn of the Screw (book)** and choose **Run a new live analysis**. New analyses use the real Qloo API. No key is entered in the browser. The original eight evaluation cases remain unchanged and expose real edge cases and coverage limits.

The separate **View recorded result** action reads one dated, authentic positive control from the [hosted jury reader](https://qloo-jury-evidence.russetpig129.chatgpt.site/). It makes no new API or model call. The interface preserves the original input, provenance and export; a separate English editorial translation helps read the original French creative text. This recorded read path uses Sites server storage and does not call the live Mac gateway. A new live analysis still needs the Mac, Qloo and the native model route.

After receiving a complete accepted result, **Choose an edit for your book**
offers two local editing proposals made from those same four shots. Their pacing
and voice entrance differ; images, story order, original words and reference
bindings remain inspectable. A silent adaptation can omit narration and reuse
existing words as captions. The author can choose either proposal, a tie, or
neither, then download a separate decision with the exact original UTF-8 export,
source hash, timing estimates and note. An input change requires a new choice.
The separate **Prepare a local sound-off adaptation** action addresses a delivery
constraint on that received result. It shows spoken words not reproduced in the
captions, proposes their transfer to screen text, and lets the author correct each
plan before explicitly accepting or rejecting it. Original timing is kept, with
warnings for fixed timing or long text. Its separate derivative ID/hash links the
exact parent, exact correction and decision; the original UTF-8 export is attached.
The native parent's sound constraint and verdict are not rewritten. Native
verification of the derivative has not run; free author text is not checked for
canon, spoilers or comprehension. Local word-rate checks do not establish those
properties. Editing again invalidates the local decision.
**Resume a saved local decision** reopens an exported sound-off decision for the
exact received parent (up to1MiB). It checks the file schema, derived identity,
payload hash, parent UTF-8 bytes and protected shot fields before restoring only
captions and the note. They return as an undecided draft: accept or reject again
before downloading. Invalid files leave the current draft and decision intact.
No URL from the file is followed. This is local integrity checking, not source
authentication or semantic/native verification; a saved historical decision is
not a current approval.
These are deterministic local recompositions of a received result, including a
dated recording, not two new Qloo/Qwen generations or rendered trailers. The
two cadences keep one scenario; distinct narrative angles remain an open product
improvement. Play either local text storyboard to inspect the image holds and
progressive received words, then stop or replay it. No audio or imagery is rendered.
The original writer review does not certify the edits. These local editing actions do not requalify the native engine or its runtime.
See the [delivered scope and original A/B/C protocol](docs/EDITORIAL-COMPARISON-PROTOCOL.md).
The [local editing comparison](docs/LOCAL-UTILITY-COMPARISON.md) records the
prepared editor's initial reopening advantage and the bounded local resume
change separately. It is a technical operator exercise, not an author study.

**Change what one shot reveals** compares one received shot with a local author
amendment, guided by the author's own intention. Image description, narration,
screen text and sound can change together; the other three shots and every
duration stay unchanged. Choose the amendment, the original or neither, then
download the selected/proposed four-shot production texts and the exact parent
separately. Choosing neither leaves no adopted storyboard. Every edit or shot/source change
requires a fresh choice. This distinct local export is not accepted by the
caption-only sound-off resume action. Qloo links and native acceptance apply to
the parent only; local canon, spoilers, constraints and comprehension still need
author review. No new generation or human/creative advantage is established.

## Current workflow

Source **2.7.0** uses a resolved book signal to ask `qloo_recommend` for movie references. The first two in Qloo's returned order are suggestions; generation waits for an explicit choice. The author can retain, remove or add a title. A fresh confirmation preserves the original proposal and the author's preference separately. A subset or reordering of the same proposal does not trigger `rank`; ranking is used only when an added entity provides new information. Physical `not_found` warnings, a generic entity without movie subtype, unusable IDs and missing affinities stop the workflow before generation. Genre tags come from received book metadata, not an invented extra tool call.

One authentic **fdbf503** case was received on 29 October: six Qloo GETs (all 200), three local Qwen role calls, 84,417 ms active and four shots totalling 38 seconds. Qloo proposed The Devil and Daniel Johnston, Grey Gardens, I Am Divine, Dark Days, Crumb and Marina Abramovic: The Artist Is Present. Claude confirmed the first two for the author; this is not evidence of Yann's personal preference. Documentary links use entity IDs: shots 1 and 3 cite the first retained film, shot 2 the second, and shot 4 remains editorial. Those links are not evidence of artistic causality.

The writer returned French despite the English James synopsis. The native typo “gouvernasse” and caption “Mais ils savent” remain unchanged, with separate editorial suggestions and English reading aid. The verifier accepted the case; independent editorial reservations remain. The preceding bff2 attempt failed our type/subtype validation after four successful GETs and zero model calls. It and all consumption remain preserved. This single integration case does not establish creative superiority, canon fidelity, human benefit or revenue.

### Earlier source changes and historical recording

Source **2.6.6** corrects a narrow lexical false rejection of explicit creature-exclusion lists. It reuses the scoped nominal-negation mask and preserves affirmative clauses introduced by comma-and/et, including coordinated subjects, while explicitly negative nor/ni joins retain scope. Targeted regressions cover exclusions, affirmative clauses, contrasts and double negatives. The targeted checks are pure offline regressions, not semantic validation, a new creative comparison or a production-time qualification.

Source **2.6.5** removes rank-position artistic obligations from the next writer’s complete SYSTEM/USER messages and per-shot input. The ranked catalogue remains documentary context, without an automatic whole-brief replacement. [The message-contract reception](docs/DOCUMENTARY-REFERENCE-CONTEXT-2.6.5.md) compares the actual constructed documents before and after, with no model call. Exported positional links remain compatibility provenance, explicitly limited; they do not prove an artistic cause. The canonical synopsis and delivery constraints are unchanged.

The certainty-preserving purpose and narrow visual-negation guard from **2.6.4** remain. Their [framing report](docs/CREATIVE-FRAMING-2.6.4.md) retains the failed deliveries, repaired replay and limited Codex comparison. Source publication and Mac activation are separate receptions. Those source changes did not inherit native qualification from **2.6.3**. The separate Sites recording remains that historical 2.6.3 result; the new 2.7.0 integration case is linked above. Inference settings remain unchanged.

The historically qualified **2.6.3** engine keeps an unseen phenomenon off-screen,
including blurred or peripheral body shapes, while permitting an ordinary
narrator's face when the brief allows it. Evidence requirements follow each
shot's actual claim: a purely editorial shot can have no Qloo reference; a
shot claiming measured Qloo support still requires a valid evidence lineage.
The verifier can still require revision or block a result. Such observations
are displayed without presenting the rejected plans or enabling their export.
The native writer can still return French creative text for an English brief.
The dated example provides a separately attributed English editorial
translation; language compliance is not claimed for every new live run.

In the **20 October recorded path**, the official Qloo MCP harness resolved public titles and ranked an explicit movie shortlist. The backend also reads the physical HTTP warning channel, because the harness can omit an upstream `not_found` warning. Every supplied seed must be usable for ranking, and every selected item must have a finite measured affinity. Partial coverage or missing scores stop the workflow before native generation.

In that historical path, the deterministic selector keeps the order returned by Qloo after checking eligibility and retains up to two movie references. It requires finite affinity values, but does not reweight them or sort their numerical magnitudes locally. For a two-reference result, the first retained reference is bound to shots 1 and 2, the second to shot 3, and shot 4 remains editorial. Those exported links are retained for compatibility and inspection. In source 2.6.5 the writer is no longer instructed to borrow from a reference because of that position; measured scores remain copied from Qloo evidence, never generated by the writer. The [jury guide](JURY-GUIDE.md#follow-a-reference-through-the-decision) explains how to inspect this chain in the hosted recording without making a new live request.

When coverage is complete, a native Hermes/Qwen analyst, writer and verifier produce and check four complete creative shots. The interface displays measured scores, selected references, evidence links, timing and the received public document. Timing, framing, captions and sound are editorial choices. Music is not measured in the current profile. No audience percentage, quality gain, conversion lift or sales forecast is claimed.

## Evaluation and corrective findings

The first integration check after the hosting changes made seven real Qloo
requests and three native role calls, then ended in `needs_revision`. Its
output remains failed: a peripheral silhouette conflicted with the unseen
presence, and the verifier also objected to a deliberately editorial final
shot. Version 2.6.3 clarifies these contracts and preserves the original
failure, its consumption and the unchanged eight-case inputs.
Its private regressions, portable synthetic controls and independent
counterexamples are distinct from the next native end-to-end run.

A subsequent public run on 20 October, `run-public-928b9561-7216-4dac-b091-2a660f0f3a1d`,
completed on version 2.6.3: seven real Qloo requests, three native role calls,
95,282 ms of active time and four complete shots. The verifier accepted the
result and structural checks passed. The downloaded browser document equals
the server public export. Creative fields were nevertheless returned in
French despite an English synopsis; that limitation remains explicit.
The previous failure and its consumption have not been reclassified.

The primary new-analysis action now sends the current complete brief with a
new idempotency key and no former parent. Only an explicit clarification
continuation retains the original parent, choices and gateway. Ten targeted
local counterexamples cover these distinctions without additional API or
model calls.

See [EVALUATION_RESULTS.json](EVALUATION_RESULTS.json) and [PHYSICAL-COVERAGE-RECEPTION.json](PHYSICAL-COVERAGE-RECEPTION.json). The earlier 2.6.1 full qualifications are withdrawn, with original outcomes preserved historically: Qloo resolves Dune and Rebecca metadata but reports their IDs as `not_found` at the ranking endpoint. C01 and C02 therefore have partial coverage. C06 has no usable ranking signal and no affinity; input order must not be presented as a measured cultural ranking.

The three incomplete-reference cases correctly make zero API/model calls. Ambiguous titles and the synthetic-title case require clarification. Version 2.6.2 was checked on the genuine archived HTTP responses, with no new inference during those regression checks. Historical response archives are retained privately, with their qualification withdrawals preserved in the public reception statistics. A separate clean-reference positive control is qualified in [PUBLIC-BROWSER-RECEPTION.json](PUBLIC-BROWSER-RECEPTION.json): 7 HTTP 200 responses, no ignored seed, 3 finite affinities, 3 native role calls, 4 complete plans and verifier acceptance. The browser download equals the server public export. This is a new custom control, not a rewritten frozen case.

## Source and architecture

Current source is in `taste-matched-trailer/`, with adjacent frozen contracts in `campagne-hackathon-2026-10-19/`. Earlier root agent files and video materials are historical. The root index and `director-config.json` serve GitHub Pages. Private credentials, runtime jobs, native receipts, raw provider payloads and machine logs are excluded.

The Python Director, official Qloo harness and existing native Hermes Studio model route run behind a private loopback backend. A separate HTTPS gateway exposes only asynchronous application jobs. POST `/api/director/run` uses an Idempotency-Key; GET `/api/director/jobs/<id>` polls the result. Explicit choices use `parent_job_id` and `resolution_choices`. Reference removal uses `{parent_job_id, entity_id}` at `/api/director/remove-reference`, then 202/poll. The gateway returns only the public export, never a private bundle. Global model settings are unchanged.

The static site does not run Python or MLX. Local reproduction requires Node 22.19+, the Qloo 0.1.26 harness, protected server credentials and the operator's qualified native Hermes/Qwen route. The private backend command is `node qloo_mcp_backend.mjs --serve --port 8787` (pass `--port 8787` as separate arguments). Its API is an internal full-bundle interface; the public frontend is connected through the gateway. No new SDK or paid model route is automatically installed.

## Availability and limits

The native backend depends on the originating Mac and its network. The fixed recorded example is also served independently through Sites; it does not use the live configuration pointer. Its deployment and expiry still limit availability, and no physical Mac-power-off test is claimed. A dedicated user service supervises the Qloo backend, application gateway and HTTPS tunnel. The stable GitHub Pages URL reads a narrowly updated `director-config.json` pointer when the tunnel changes. User-service startup can resume after login; it does not bypass FileVault, unlock the keychain or keep a session alive after logout. No uninterrupted availability through the end of judging is guaranteed.

Runtime **1.2.0** adds exact backend/gateway version gates and refuses to adopt live processes from a different release or source manifest. Five targeted offline tests cover those gates. It retains the **1.1.3** logic that renews the public pointer from its actual expiry, including after a restart that needs no immediate publication. Admission closes on invalid or expired metadata, and its short lease cannot extend beyond the pointer. The original six pure checks cover that expiry correction. A controlled application restart receives the new process identities and preserves the persistent family/job state; it makes no new Qloo or model call. See [the runtime delta and its limits](RUNTIME-UPDATE-20261020.json) and [current source pins](runtime/SOURCE-PINS.json). `RELEASE-MANIFEST.json` remains the historical 2.6.2 snapshot.

The gateway serves only its fixed application routes. Its original recorded-result GET routes remain available for the operator, but the public frontend now reads the fixed example through the separate Sites reader. Sites verifies the server-stored bytes and expiry and performs no Qloo or model work. A missing or invalid recording produces an explicit error. The public source contains neither the response cache nor private runtime files.

Live admission can be paused before reserving a run family, for example during Studio rendering. A guard-health response alone never proves that future compute is available. Known jobs survive a tab reload through GET-only recovery at their original gateway; an unknown submission outcome blocks duplicate submission. Dead process locks are reconciled conservatively, while an uncertain in-flight outcome is fenced rather than replayed.

The initial public pool is 10 run families, 140 physical requests and 30 native role calls, with four families per IP per hour, serial execution and no automatic refill. The change from two to four per IP preserved every existing family, reservation and consumed call. Unknown outcomes stop the service for reconciliation; a restarted process cannot reset its budget.

The [official developer guide](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide) allows private server-side caching and prohibits storing Qloo response data in a public repository. API-derived rows have therefore been removed from the current public checkout while original private receipts, counts and input cases are preserved. Old Git objects have not been rewritten; removal from the current checkout is not a claim of complete historical erasure.

## License and primary sources

MIT; preserve the repository LICENSE and rights for existing assets.

- [Qloo official hackathon kit](https://github.com/qloo/qloo-hackathon-kit)
- [Submission requirements](https://qloo.devpost.com/)
- [Official rules](https://qloo.devpost.com/rules)
