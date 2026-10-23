"""Return one saved first writer response through strict native schema and real Role2.

No inference. A successful local replay is not a native Qwen/app qualification.
Raw first response remains unchanged; existing validator normalization is recorded.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from capture_scaffold_inputs import PARENT_HASH, canonical, capture, load, sha


def replay(director, runner, case, cases, parent, saved_text, expected_capture):
    rebuilt = capture(director, runner, case, cases, parent)
    if rebuilt["messages"] != expected_capture["messages"]:
        raise ValueError("Writer input differs from frozen captured messages")
    parsed = runner.strict_json_object(saved_text)
    normalized = runner.validate_role_output("role_2_creative_redactor", parsed)
    # The pure validator adds its historical native route label. It is not an
    # observation of the saved writer's provider and must never be inherited.
    normalized.pop("model_route_version", None)
    callbacks = []

    def saved_runner(role, payload):
        if role != "role_2_creative_redactor" or payload != expected_capture["payload"] or callbacks:
            raise ValueError("Unexpected or duplicate replay callback")
        callbacks.append(role)
        return copy.deepcopy(normalized)

    constraints = {**cases["common_constraints"], **case["constraints"]}
    validated = director.validate_brief(case["synopsis"], ["The Turn of the Screw (book)"], constraints)
    budget = director.make_initial_run_budget("run-scaffold-" + case["id"], 0, 1)
    brief, directions = director.llm_role_2_creative_redactor(
        budget["run_id"], "recorded_live", validated, copy.deepcopy(cases["analysis"]),
        copy.deepcopy(parent.get("evidence_sources", [])), copy.deepcopy(parent["decisions"]),
        budget, False, saved_runner)
    errors = director.validate_constraint_fidelity(brief)
    expected_plans = expected_capture["payload"]["shot_plan"]
    for shot, plan in zip(brief["shots"], expected_plans):
        binding = plan["retained_reference"]
        expected_ids = [binding["entity_id"]] if binding else []
        if shot["retained_entity_refs"] != expected_ids:
            raise ValueError("Returned core changed frozen reference binding")
    return {"schema_status": "pass", "deterministic_constraint_errors": errors,
            "deterministic_status": "pass" if not errors else "fail",
            "brief": brief, "directions": directions,
            "normalization": "Existing strict validator strips field whitespace and adds direction IDs/origin. Raw first response retained separately; no content repair or retry.",
            "callback_count": len(callbacks), "application_counter_in_memory": budget["llm_calls_used"],
            "model_calls_in_this_replay": 0, "Qloo_calls": 0, "native_model_executed": False,
            "generation_origin_scope": "Core consumes saved Codex output through llm_runner; llm_role_2 generation labels describe this function path, not a new native/model call.",
            "native_acceptance": "not_executed", "semantic_certainty_review": "requires_independent_reader",
            "full_application_or_cultural_acquisition_qualified": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--director", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--variant", choices=["old", "candidate"], required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.out.resolve().is_relative_to(root):
        raise ValueError("Keep response/provider-derived data outside source checkout")
    receipt = json.loads((args.captures / "CAPTURE-RECEIPT.json").read_bytes())
    expected_sha = receipt["sources"]["baseline_director" if args.variant == "old" else "candidate_director"]
    if sha(args.director.read_bytes()) != expected_sha or sha(args.parent.read_bytes()) != PARENT_HASH:
        raise ValueError("Frozen source or parent changed")
    cases_path = Path(__file__).with_name("scaffold_cases.json")
    runner_path = root / "taste-matched-trailer/guarded_qwen_runner.py"
    if sha(cases_path.read_bytes()) != receipt["sources"]["cases"] or sha(runner_path.read_bytes()) != receipt["sources"]["runner_unchanged"]:
        raise ValueError("Frozen cases or runner changed")
    cases = json.loads(cases_path.read_bytes())
    case = next(c for c in cases["cases"] if c["id"] == args.case)
    item = next(c for c in receipt["captures"] if c["case"] == args.case and c["variant"] == args.variant)
    capture_raw = (args.captures / item["file"]).read_bytes()
    if sha(capture_raw) != item["sha256"]:
        raise ValueError("Captured message artifact changed")
    response_raw = args.response.read_bytes()
    director = load("saved_scaffold_director", args.director)
    runner = load("saved_scaffold_runner", runner_path)
    try:
        if len(response_raw) > 16000:
            raise runner.AdapterContractError("Saved output exceeds native byte bound")
        try:
            saved_text = response_raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise runner.AdapterContractError("Saved output is not UTF-8") from None
        result = replay(director, runner, case, cases, json.loads(args.parent.read_bytes()), saved_text, json.loads(capture_raw))
    except runner.AdapterContractError as exc:
        result = {"schema_status": "fail", "error_type": type(exc).__name__, "error_reason": str(exc), "deterministic_status": "not_run", "model_calls_in_this_replay": 0, "Qloo_calls": 0, "native_acceptance": "not_executed", "creative_result_repaired": False}
    result["provenance"] = {"case": args.case, "variant": args.variant, "director_sha256": expected_sha,
        "captured_input_sha256": item["sha256"], "first_response_sha256": sha(response_raw),
        "response_source": "saved first Codex writer response; model/effort observations owned by root dispatcher",
        "replay_tool_sha256": sha(Path(__file__).read_bytes())}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "FIRST-RESPONSE-UNCHANGED.txt").write_bytes(response_raw)
    (args.out / "CORE-REPLAY-RECEIPT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ["schema_status", "deterministic_status", "native_acceptance", "provenance"]}, ensure_ascii=False, indent=2))
    return 0 if result["schema_status"] == "pass" and result["deterministic_status"] == "pass" else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    def offline_only(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
            raise RuntimeError("Saved replay forbids network, clients and subprocesses")
    sys.addaudithook(offline_only)
    raise SystemExit(main())
