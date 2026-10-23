"""Prepare private comparison packets from the exact already-public parent export.

No provider, key, model, package installation or mutable runtime access.
Generated evidence/packets stay outside this public source checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT_HASH = "53b2f25bdfc431a2567ef7af4f1b9d51282ca62904a7e121dc484e1985c0435d"
PARENT_RUN = "run-public-928b9561-7216-4dac-b091-2a660f0f3a1d"
EDIT = "Une trace matérielle. Une pression contre la réalité."

COMMON_INSTRUCTION = """You are a capable creative editor helping an author choose an actionable sound-off trailer brief.
This is an offline matched text-production task. Use only this packet and your general cultural knowledge. Do not browse, call tools or APIs, claim execution of a kit/application, or invent measurements, native verification, rendered media, audience percentages or sales effects.
Treat the supplied synopsis as the entire story canon. The named book is a cultural reference, not permission to import its plot, characters or ending. Preserve uncertainty. Never show any form of the unseen presence, including a blurred/peripheral body. An ordinary narrator is allowed. Do not add plot events, named characters or a revealed explanation.
Write in English. Produce one usable 38-second,16:9,sound-off four-shot brief, with fixed intervals0–9.5,9.5–19,19–28.5,28.5–38 seconds. Voiceover and sound fields must be empty. Screen text at most12 words per shot; propose images without claiming footage or a rendered film exists. Select at most two films from the common unranked catalogue and justify their relevance to this specific brief. Cultural associations do not validate a new caption or a causal claim.
Return ONLY a JSON object, at most500 whitespace-separated words in the complete output. Use this same structure:
{"reference_choices":[{"title":"...","why_for_this_brief":"...","basis":"editorial knowledge or supplied dated evidence"}],"shots":[{"id":"shot_01","start":0,"end":9.5,"image":"...","screen_text":"...","voiceover":"","sound":"","reference_titles":[],"evidence_basis":"..."}],"author_decision":{"recommended_action":"...","specific_reason":"...","remaining_defect":"..."},"constraint_review":{"scope":"editorial self-check only","remaining_risks":[]}}
Supply all four shots. Include one concrete next author decision and its remaining weakness. Honest uncertainty, an editorial-only shot and a reasoned limitation are preferable to invented support. Do not name the experimental condition in your answer.
"""

KIT_CONTEXT = """Official-kit context, documented capabilities rather than a tool execution:
The public Qloo harness exposes entity/tag resolution and a confirmation step before taste queries. qloo_rank accepts a typed shortlist and taste signals; recommendation, audience comparison, demographics, trends and geographic popularity are other workflows. Its qloo explore chat route uses a model-provider sign-in; CLI and MCP are also available. CLI, chat and MCP share normalized workflow results. The documented statuses distinguish ok, empty, needs_input, partial, degraded and error; incomplete or ambiguous evidence needs attention rather than a fabricated ranking. A direct API route is separate from normalized workflows. These capabilities already exist in the official kit. Here you receive dated public fields below; no kit call is being run. Use the supplied information competently, explain choices and distinguish measured association from your own creative interpretation.
Sources: https://github.com/qloo/qloo-hackathon-kit ; https://github.com/qloo/qloo-hackathon-kit/blob/main/starter/mcp-client/README.md ; https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/SAFE_USE.md
"""

APP_CONTEXT = """Application context, documented policy rather than an application or native-verifier execution:
The application's det-select-v1.5 keeps up to two eligible movie references in the order returned by Qloo, requiring finite measured affinities. It does not rerank numerical magnitudes. Its native four-shot scaffold binds the first retained reference to shots1–2, the second to shot3, and leaves shot4 editorial. For this packet preserve those bindings while writing original proposed shot text. Open the uncertainty, develop a material trace, make an emotional turn, then invite reading without a reveal. The local sound-off delivery layer keeps source/proposed text, allows author correction and acceptance/rejection, and exports an identity linked to the historical parent. Its structural and word-rate checks do not assess comprehension or canon. A derivative has no native acceptance merely because the parent was accepted. Your response here remains offline editorial output; no actual app role or verifier runs.
Source: https://github.com/yannabadie/taste-matched-trailer/tree/8145ac6708fd05043109aec841e1375cdd6bc671
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    if out == root or out.is_relative_to(root):
        raise ValueError("Public provider-derived fields and packets must remain outside the public checkout")
    raw = args.parent.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PARENT_HASH
    parent = json.loads(raw)
    assert parent["run_id"] == PARENT_RUN
    rows = [{key: row[key] for key in ("name", "entity_id", "entity_type", "returned_order", "score_field", "score_value")}
            for decision in parent["decisions"] for row in decision["candidates"]]
    common = {"synopsis": parent["brief"]["synopsis"],
              "cultural_book_reference": "The Turn of the Screw (book)",
              "movie_catalogue_unranked_alphabetical": sorted(row["name"] for row in rows),
              "original_native_constraints": parent["brief"]["user_constraints"],
              "local_task_constraint": {"sound_off": True, "duration_seconds": 38, "aspect_ratio": "16:9"},
              "original_images_or_native_writer_text_supplied": False}
    evidence = {"kind": "dated_public_reader_fields_not_raw_HTTP_or_cache",
                "source": "https://qloo-jury-evidence.russetpig129.chatgpt.site/",
                "original_run_id": PARENT_RUN, "created_at": parent["brief"]["created_at"],
                "parent_public_export_sha256": PARENT_HASH,
                "ranked_movie_observations": rows,
                "limits": "Associations among public cultural entities. No measured manuscript fit, creative preference, caption quality or audience outcome."}
    out.mkdir(parents=True, exist_ok=True)
    def dump(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    dump("COMMON-BRIEF.json", common)
    dump("PUBLIC-EVIDENCE-BC.json", evidence)
    packets = {
        "A": COMMON_INSTRUCTION + "\nCOMMON BRIEF\n" + json.dumps(common, ensure_ascii=False, indent=2) +
             "\nCONTEXT\nNo measured provider evidence is supplied. Use competent editorial/cultural knowledge; label it as such. No lower-quality instruction is intended.\n",
        "B": COMMON_INSTRUCTION + "\nCOMMON BRIEF\n" + json.dumps(common, ensure_ascii=False, indent=2) +
             "\nKIT CONTEXT\n" + KIT_CONTEXT + "\nDATED PUBLIC EVIDENCE\n" + json.dumps(evidence, ensure_ascii=False, indent=2),
        "C": COMMON_INSTRUCTION + "\nCOMMON BRIEF\n" + json.dumps(common, ensure_ascii=False, indent=2) +
             "\nKIT CONTEXT\n" + KIT_CONTEXT + "\nAPPLICATION CONTEXT\n" + APP_CONTEXT + "\nDATED PUBLIC EVIDENCE\n" + json.dumps(evidence, ensure_ascii=False, indent=2),
    }
    inventory = []
    for condition, prompt in packets.items():
        filename = "PACKET-" + condition + ".txt"
        (out / filename).write_text(prompt)
        inventory.append({"condition": condition, "file": filename, "characters": len(prompt),
                          "whitespace_words": len(prompt.split()), "sha256": hashlib.sha256(prompt.encode()).hexdigest()})
    dump("PACKET-INVENTORY.json", {"status": "PREPARED_NOT_EXECUTED", "conditions": inventory,
        "common_instruction_sha256": hashlib.sha256(COMMON_INSTRUCTION.encode()).hexdigest(),
        "same_output_word_limit": 500, "actual_model_tokens_or_compute": "not_received",
        "proposed_fresh_context_order": ["B", "A", "C"],
        "required": ["Fresh isolated conversation for each condition; prior CGPro review contains evidence and would contaminate A.",
                     "Same visible model/effort settings; record what UI exposes and no invented per-call parameter.",
                     "One first answer per condition; preserve failure, refusal and format errors. No condition-specific improvement retry.",
                     "Offline information/contract comparison, not actual kit/app/native execution or a user study."]})
    dump("TASKS.json", {"kind": "technical_operator_tasks_not_author_preferences", "authentic_cultural_cases": 1,
        "parent_run": PARENT_RUN, "parent_sha256": PARENT_HASH,
        "tasks": ["Inspect which received spoken word sequences are absent from captions", "Make a silent draft retaining source images/order/durations", "Set shot_02 to the exact shared target and accept/export", "Edit again, observe old decision invalidation, reject/export", "Close/reopen and continue from the saved file without retyping the exact correction", "Refuse a changed-parent negative control"],
        "shared_caption_target": EDIT, "shared_rejection_target": "Une trace matérielle.",
        "baseline": "Reader/export plus competent JSON text editor, validation/hash and persisted file; reusable independent script allowed and setup reported separately.",
        "workbench": "Published8145 source in a network-disabled local replay; root-owned public/native state unchanged.",
        "outcomes": ["exact task completion", "manual recovery/copying", "provenance/identity checks", "ability to reopen", "operator operations and setup separately"],
        "not_outcomes": ["human time", "customer preference", "better art", "causal provider benefit"],
        "counterexamples": "Synthetic state mutations stay separate from the one authentic cultural case."})
    print(json.dumps(inventory, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
