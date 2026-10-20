# Cultural Launch Director

A Qloo-powered working prototype for choosing explainable cultural references for a book and turning those choices into a creative trailer brief.

The workflow separates the book’s intent, Qloo’s aggregate cultural associations, the selection decision, and the writer’s creative interpretation. Affinity is not an individual probability, a sales forecast, or proof of commercial positioning.

## Try the application

The existing public frontend is hosted at [GitHub Pages](https://yannabadie.github.io/taste-matched-trailer/). The 2.6.1 release connects to an application-only HTTPS gateway. A temporary gateway depends on the originating Mac and tunnel remaining available; its uptime through the judging period is not established by a local test.

1. Choose **Your own brief**, a frozen evaluation case, or the separately labelled historical-input demonstration.
2. Review the brief and public reference titles. The public gateway supports **Live** only; fixtures and archived replay are private-tool modes.
3. Click **Create the brief**. Queued and running jobs are followed by status reads; the browser does not silently resubmit a POST.
4. If a title is ambiguous, select a candidate and click **Continue with selected references**. This is an explicit new request linked to the preceding job.
5. Inspect the returned scores, selection decisions, creative plans and sources. Removing a selected reference waits for server confirmation and shows the updated dependency state.
6. Download the exact public document received for the displayed run. Failed or blocked results cannot be exported as a successful brief.

The eight frozen cases remain unmodified. Their original French wording is accompanied by an English translation. A custom edit is a separate request, not a successful execution of an unchanged evaluation case. Availability of all eight cases in the interface does not mean all eight have passed live evaluation.

## Modes and evidence

The public interface and gateway accept **Live only**. The other options are disabled and rejected locally before a request. The private CLI/backend can support fixture and recorded-live workflows separately; those full bundles are not the public UI contract.

- **Live** requests new evidence. A live-mode label alone does not prove an authenticated useful result. The public source references and the server’s lineage checks determine that claim; complete private receipts remain server-side.
- **Recorded live** uses a dated, authentic archive when the server has one; it does not establish current API availability.
- **Fixture** is a synthetic illustration, never an authentic Qloo observation.

The Turn of the Screw demonstration uses one book UUID and three movie UUIDs from the dated qualification of 19 October 2026 as fixed reference inputs. They are explicitly attributed as historical inputs. Only a new run’s returned evidence can support a fresh ranking claim.

No conversion improvement, audience split, invented affinity percentage, commercial-comparable quality or market validation is claimed. The dated video illustration predates the application’s authenticated run and is not output from the current run.

## Frontend configuration

The buildless `index.html` reads `director-config.json` next to it:

```json
{ "api_base_url": "https://YOUR-APPLICATION-GATEWAY" }
```

Use the actual app-only HTTPS gateway. This is a public URL, not a secret. Never put a Qloo key, model key, bearer credential or password in this file or the frontend.

With an empty value, the frontend can use its own HTTP(S) origin only when that origin is the **public application gateway**. The private backend server is a different contract and must not be used as this public UI’s API base. GitHub Pages without a configured gateway remains visibly unavailable for runs.

GitHub Pages hosts the static interface. It does not run Python, MLX, the Qloo stdio harness or the local model. The backend and model route must be prepared separately by the operator. The local full workflow uses the already guarded model route; this frontend does not start or configure a model.

## Private local tools and the public interface

The private Node/Python backend and CLI are operator/development tools. They can return a complete internal bundle with detailed evidence, runtime data and private receipt fields. Keep that service on loopback and outside public access.

For example, the private backend can be started by its operator with the already configured runtime:

```sh
node qloo_mcp_backend.mjs --serve --host 127.0.0.1 --port 8787
```

This command starts the **private backend**, not the public gateway. Even if that server serves `index.html`, its direct API response is not the whitelisted `public_export` this interface expects. Do not treat opening port 8787 as a working public demo or expose it directly.

The public interface is served by GitHub Pages or the application gateway and uses `director-config.json` to address that gateway. The gateway submits work to the protected backend, returns jobs and exposes only the whitelisted public result. The public UI never requests or accepts a full private bundle.

Fixture/recorded-live diagnostics remain in the private CLI/offline workflow. Follow the official Qloo kit for the event credential and harness, and configure them only through protected server mechanisms. The native model route and CPU tokenizer remain behind the existing guard; the interface never starts or configures them.

The operator must receive the exact gateway/backend/guard combination and enforce app-only paths, the permitted frontend origin and server budgets before external use. Never expose the model guard, arbitrary files or private receipts.

## Backend contract

- `POST /api/director/run`, with `Idempotency-Key`, accepts the brief, public references, confirmed IDs, ranking domains, shortlist options, constraints and mode. Frozen cases add `frozen_case_id`.
- A `202` response provides `job_id`, `status` and `poll_url`. `GET /api/director/jobs/<id>` is polled every three seconds. `queued` and `running` are not successful results. Terminal states include `needs_input`, `completed` and `failed`.
- A `200` response containing the same whitelisted `public_export` directly is accepted for compatibility. A private backend full bundle is not accepted.
- Explicit disambiguation sends `confirmed_entity_ids`, an object `resolution_choices` mapping the original server-returned query strings to chosen IDs, and `parent_job_id`. The server validates candidates against its stored authentic parent result and supplies provenance.
- `POST /api/director/remove-reference` sends `parent_job_id` and `entity_id` with a new Idempotency-Key for the explicit action, then follows the same `202` job polling contract. The browser’s bundle is not trusted as server state.
- Public results must be expurgated server-side. Full private evidence, filesystem paths and credentials are not public exports.

The server owns physical Qloo limits, the common model budget, one-operation concurrency, authentic provenance and public access controls. The browser cannot establish those guarantees.

## Validation and limitations

Frontend contract receipts record the focused synthetic checks for each revision, including public-export rendering, jobs and clarification. The latest Live-only gate was checked locally without a live call. This is not a live API, model, server, browser or layout qualification. Live case results and the final external browser reception must be documented by their exact version and receipt. Prior successful local runs do not qualify a changed release automatically.

Setup of the Node/Python backend, official Qloo harness, protected credential and native local model route is an operator task. The event kit requires Node.js 22.19 or newer and Qloo harness 0.1.26 or newer; record exact versions used. Do not run arbitrary fixture data as live evidence.

## License and sources

MIT. Preserve the repository’s LICENSE and rights for bundled assets.

- [Official Qloo hackathon kit](https://github.com/qloo/qloo-hackathon-kit)
- [Submission requirements](https://qloo.devpost.com/)
- [Official rules](https://qloo.devpost.com/rules)

## Release layout and access

The current source is in `taste-matched-trailer/`, with its adjacent frozen `campagne-hackathon-2026-10-19/` contracts. Earlier root agent files and dated media remain historical. The root index and configuration serve GitHub Pages. Private credentials, native receipts, runtime jobs, machine logs and raw Qloo responses are excluded. `evidence/*-recorded.json` contains explicitly dated exports, never automatic LIVE fallbacks.

The Mac hosts the private backend and native model; the public gateway exposes only application jobs. Its first public allowance is 10 families / 140 physical requests / 30 native calls, with no automatic refill. It requires the Mac and tunnel to remain online. There is no reboot autostart or guaranteed availability through the 17 November 2026, 05:45 Paris end of judging. The page remains at its stable GitHub Pages URL if the temporary tunnel stops.

## Public browser reception

On 20 October 2026, the published GitHub Pages interface completed a fresh C02 request through the HTTPS gateway: 10 authenticated Qloo HTTP responses, 3 native role calls, 4 complete plans and verifier acceptance. The downloaded public JSON exactly matched the server export. See PUBLIC-BROWSER-RECEPTION.json. The Devpost description, pitch and links were updated and read back on the public page; the existing submission remains submitted.
