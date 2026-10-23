# Jury guide

Open the application at **https://yannabadie.github.io/taste-matched-trailer/**.
No Qloo key, local installation or personal account is required in the public
application.

For the dated result, open the **[hosted jury reader](https://qloo-jury-evidence.russetpig129.chatgpt.site/)** directly or choose **View recorded result** in the application. Recorded reading makes no new API or model call.

## What this application produces

Cultural Launch Director turns a creative brief and a cultural reference into
an evidence-linked, four-shot creative brief. Qloo resolves the references and
provides measured affinities for an explicit movie shortlist. Native
Hermes/Qwen analyst, writer and verifier roles interpret and check those
measurements when a complete live run can be admitted.

The output is a creative brief, not a rendered trailer. Timing, framing, sound
and captions are editorial choices; the current profile measures movie
affinities, not music affinities or audience demographics.

The current live engine is version 2.6.3. Its writer and verifier distinguish
an intentionally editorial shot from a claim of Qloo-backed evidence, and
keep the unseen phenomenon off-screen. A requested revision remains visible
as an unqualified result. The saved example below retains its original
version 2.6.3, execution date and French native creative text. A separate
English editorial translation helps inspect it; automatic English output
is not guaranteed for new live runs.

## Inspect the received result

The independently received example uses **The Turn of the Screw (book)**.
Its original execution completed on 20 October 2026 at approximately 13:32 UTC.
It made seven successful Qloo HTTP requests and three native role calls,
received three finite measured affinities, and produced four complete shots
with verifier acceptance and structural checks passing. Active time was
95,282 ms. The English synopsis nevertheless produced French creative text.
The English reading aid is an attributed editorial translation, not another
model output or fresh API response.

The aggregate receipt is [JURY-RELIABILITY-RECEPTION.json](JURY-RELIABILITY-RECEPTION.json).
Its run identifier is
`run-public-928b9561-7216-4dac-b091-2a660f0f3a1d`.
The browser download was compared with the server's public export. The saved
example also preserves those exact original bytes for download.
The earlier 2.6.2 positive control and its [original browser receipt](PUBLIC-BROWSER-RECEPTION.json)
remain historical evidence and have not been rewritten.

A displayed recording of this result is historical evidence, served from
protected Sites server storage through the separate jury reader. The original
response data is not included in the public source checkout. Viewing it does
not make a new Qloo request, run a model, or establish that new live analysis is
currently available. Its execution date, version and provenance are retained.
The Mac-cache wording in the preserved manifest describes the original capture;
the current read path uses Sites. The original bytes have not been rewritten.

## Follow a reference through the decision

In the hosted recording, compare each candidate's returned position and finite
affinity with the selected reference IDs. The selector follows the received
order after eligibility checks; it does not reweight or locally sort the
numerical affinity values.

Then follow a selected ID into the individual shots. For a two-reference
result, the first reference is bound to shots 1 and 2, the second to shot 3.
Shot 4 is an editorial close with no Qloo reference. The exported document
preserves the decision and evidence links, so the source of a reference can
be distinguished from the writer's camera, sound and wording choices.

This is the product's useful distinction: I can inspect why a reference was
selected before deciding whether to use the creative interpretation. Finite
affinities and returned order establish this data dependency; they do not
establish that the resulting creative text is better than a model-only brief.
Reading this chain in the recording makes no new Qloo request or model call.

## Make a local editorial choice first

Once the recorded example or an accepted live result is visible, open **Choose
an edit for your book**. Compare **Let the images lead** and **Let the words lead**:
their full timelines use the source's actual images and words, with different
shot durations and voice entrance. Neither option is recommended by an affinity
score. These are local deterministic recompositions of the displayed source, not
two model runs. A dated source stays dated.
These are two cadences of the same scenario, not two separate narrative angles.
Use either **Play / replay** button to see four received image descriptions and
progressive received words over the selected timeline. Stop ends that playback;
replay starts from the beginning. This text storyboard produces no image, video
or spoken voice and does not choose your export.

Inspect the complete proposals and any timing warning. Choose an option, a tie,
or neither, optionally explain why, then download the editing decision. The file
keeps the original document and exact UTF-8 export, source hash, constraints,
alternatives, sound state and your note. The original result can still be
downloaded separately with its original bytes. No preference is recorded on a
server. Changing inputs clears the current choice; an earlier exported choice
belongs to its historical source.

Original creative words keep their original language; English edit instructions
are not a translation. Sound-off edits may omit narration rather than invent
new captions. Timing uses an explicit word-rate estimate, not a received audio
render. Fixed individual shot timing or missing words can prevent these two
options; an explicit refusal is preferable to a generic invented trailer.
Author benefit and A/B/C superiority have not been measured.

## Try a new live analysis

1. Use the default custom brief and **The Turn of the Screw (book)** as the
   sole initial reference.
2. Submit a new live analysis and wait for the asynchronous result.
3. Inspect the measured affinities, selected references and four-shot brief.
4. Download the public result to inspect the evidence and limitations.

An unavailable service, exhausted demonstration allowance, ambiguous title,
unsupported reference or incomplete Qloo response is shown as such. A failed
live request must not be silently replaced with a recorded result.

The live service uses protected server credentials. Never enter an API key,
personal document or private client material into the public brief.

## Understand the eight evaluation cases

The eight original cases remain frozen. Five require missing information,
reference clarification or rejection of an invented title. C01 and C02 expose
partial ranking coverage; C06 provides no usable ranking affinity. Metadata
resolution is not treated as proof that Qloo can rank from that reference.

The earlier complete qualifications for those three cases in version 2.6.1
were withdrawn after examining raw HTTP warnings. Version 2.6.2 propagates
these warnings and stops before generation when coverage or measured scores
are missing. The clean positive control above is a separate case.

See [EVALUATION_RESULTS.json](EVALUATION_RESULTS.json) and
[PHYSICAL-COVERAGE-RECEPTION.json](PHYSICAL-COVERAGE-RECEPTION.json).

## Availability

The public page, guide and aggregate reception statistics are served by
GitHub Pages. Reading the saved example uses the separate Sites reader and
does not call the Mac service. That path still depends on Sites availability
and expires on17November2026 at04:45UTC. No physical Mac-power-off test has
been performed. A new native analysis depends on the operator's Mac, network,
protected Qloo access, backend and available local compute.

The demonstration has persistent request and model allowances. Restarting a
service does not replenish them. A visible status check is not an end-to-end
Qloo or model test. No uninterrupted-uptime guarantee is claimed.

## Competition references

The current submission deadline is 30 October 2026 at 23:45 EDT
(31 October at 04:45 in Paris). The judging period ends on 16 November at
23:45 Eastern Time (17 November at 05:45 in Paris).

The official requirements call for an externally accessible working project,
free testing access through the end of judging, an open-source repository
with instructions, and English materials or English translations. A video is
not required by the current overview.

Sources: [Qloo Agentic Hackathon](https://qloo.devpost.com/) and
[official rules](https://qloo.devpost.com/rules), checked on 20 October 2026.

The linked [official developer guide](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide)
allows private server-side caching and prohibits storing Qloo response data
in a public repository. Current source excludes these caches. Previously
published Git objects have not been rewritten; no complete historical erasure
is claimed.
