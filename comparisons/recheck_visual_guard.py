"""One countercheck of the same six saved outputs under a common guard fix.

Preserves initial sources, raw responses and failed receipts. No model/provider.
The same new guard functions are placed in both source arms; purposes stay frozen.
"""
import argparse
import ast
import json
from pathlib import Path
import sys
from capture_scaffold_inputs import canonical, load, sha
from replay_scaffold_output import replay


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evaluation", type=Path, required=True)
    p.add_argument("--parent", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.out.resolve().is_relative_to(root): raise ValueError("Keep responses outside checkout")
    args.out.mkdir(parents=True, exist_ok=False)
    candidate_raw = (root / "taste-matched-trailer/cultural_launch_director.py").read_bytes()
    candidate_text = candidate_raw.decode()
    common = candidate_text[candidate_text.index("_PERSON_VISUAL_NOUN ="):candidate_text.index("def llm_role_2_creative_redactor")]
    old = (args.evaluation / "BASELINE-DIRECTOR-2.6.3.py").read_text()
    old = old[:old.index("def _visible_phenomenon_form")] + common + old[old.index("def llm_role_2_creative_redactor"):]
    old = old.replace('2.6.3-invisible-presence-editorial-contract-20261020', '2.6.3-baseline-common-negation-fix-20261023')
    ast.parse(old)
    files = {"old": (args.out / "BASELINE-WITH-COMMON-GUARD.py", old.encode()),
             "candidate": (args.out / "CANDIDATE-WITH-COMMON-GUARD.py", candidate_raw)}
    modules = {}
    for arm, (file, data) in files.items():
        file.write_bytes(data); modules[arm] = load("common_guard_" + arm, file)
    runner_file = root / "taste-matched-trailer/guarded_qwen_runner.py"
    runner = load("common_guard_runner", runner_file)
    cases = json.loads((root / "comparisons/scaffold_cases.json").read_bytes())
    parent = json.loads(args.parent.read_bytes())
    frozen = json.loads((args.evaluation / "inputs/CAPTURE-RECEIPT.json").read_bytes())
    assert sha(args.parent.read_bytes()) == frozen["sources"]["parent"]
    assert sha(runner_file.read_bytes()) == frozen["sources"]["runner_unchanged"]
    assert sha((root / "comparisons/scaffold_cases.json").read_bytes()) == frozen["sources"]["cases"]
    mapping = json.loads((args.evaluation / "root-mapping/PRODUCTION-ORDER-v1.json").read_bytes())
    mapped = {r["opaque_id"]: r for r in mapping["order"]}
    delivery = json.loads((args.evaluation / "REVIEW-DELIVERY-v1.json").read_bytes())
    rows = []
    for row in delivery["rows"]:
        ident = row["opaque_id"]; assignment = mapped[ident]
        raw = Path(row["response_file"]).read_bytes(); assert sha(raw) == row["response_sha256"]
        capture_item = next(c for c in frozen["captures"] if c["case"] == assignment["case"] and c["variant"] == assignment["variant"])
        expected_raw = (args.evaluation / "inputs" / capture_item["file"]).read_bytes()
        assert sha(expected_raw) == capture_item["sha256"]
        expected = json.loads(expected_raw)
        case = next(c for c in cases["cases"] if c["id"] == assignment["case"])
        result = replay(modules[assignment["variant"]], runner, case, cases, parent, raw.decode(), expected)
        result["replay_provenance"] = {"opaque_id": ident, "raw_sha256": sha(raw),
            "director_sha256": sha(files[assignment["variant"]][1]), "common_guard_sha256": sha(common.encode()),
            "original_frozen_capture_unchanged": True, "first_response_changed": False, "model_calls": 0}
        target = args.out / ident; target.mkdir()
        (target / "FIRST-RESPONSE-UNCHANGED.txt").write_bytes(raw)
        (target / "CORE-REPLAY-AFTER-COMMON-GUARD.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        before = json.loads((args.evaluation / "core-replay" / ident / "CORE-REPLAY-RECEIPT.json").read_bytes())
        rows.append({"opaque_id": ident, "raw_sha256": sha(raw), "schema_before": before["schema_status"], "schema_after": result["schema_status"],
            "deterministic_before": before["deterministic_status"], "errors_before": before.get("deterministic_constraint_errors", []),
            "deterministic_after": result["deterministic_status"], "errors_after": result["deterministic_constraint_errors"],
            "native_model_verdict": "not_executed", "raw_response_and_initial_receipt_unchanged": True})
    receipt = {"status": "COMMON_NEGATION_GUARD_COUNTERCHECK_NO_NEW_GENERATION", "same_guard_in_both_arms": True,
        "common_guard_sha256": sha(common.encode()), "first_sources_and_scores_retained": True,
        "baseline_countercheck_source_sha256": sha(files["old"][1]), "candidate_countercheck_source_sha256": sha(candidate_raw),
        "script_sha256": sha(Path(__file__).read_bytes()), "new_model_or_Qloo_calls": 0, "rows": rows}
    (args.out / "COMMON-GUARD-COUNTERCHECK.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    (args.out / "OPAQUE-BEFORE-AFTER.json").write_text(json.dumps({k: receipt[k] for k in ["status", "same_guard_in_both_arms", "first_sources_and_scores_retained", "new_model_or_Qloo_calls", "rows"]}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"source_sha256": sha(candidate_raw), "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    def offline_only(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}: raise RuntimeError("Countercheck forbids network and subprocesses")
    sys.addaudithook(offline_only)
    main()
