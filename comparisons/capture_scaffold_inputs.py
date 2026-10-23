"""Execute the real writer-input path and capture, never generate creative output.

Baseline/current source imports are inert; the callback stops before generation.
Native messages are built by the existing build_messages function, not rewritten.
Only an exact already-public parent may supply historical cultural context.
Generated payloads stay outside the public checkout. No model/client/tokenizer.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

PARENT_HASH = "53b2f25bdfc431a2567ef7af4f1b9d51282ca62904a7e121dc484e1985c0435d"
BASELINE_HASH = "3e85c1d7e725d97fa6d9a9df567a9da4542442a61f42f856d340c0cc9848c5ed"
ENVELOPE = "Execute the creative-redactor role specified by the exact SYSTEM and USER messages below. Use no tools. Return only the requested JSON object."


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def load(name, source):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CapturedWithoutGeneration(Exception):
    pass


def capture(director, runner, case, document, parent):
    constraints = {**document["common_constraints"], **case["constraints"]}
    validated = director.validate_brief(case["synopsis"], ["The Turn of the Screw (book)"], constraints)
    budget = director.make_initial_run_budget("run-scaffold-" + case["id"], 0, 1)
    captured = {}

    def stop_before_generation(role, payload):
        captured.update(role=role, payload=copy.deepcopy(payload))
        raise CapturedWithoutGeneration()

    try:
        director.llm_role_2_creative_redactor(
            budget["run_id"], "recorded_live", validated,
            copy.deepcopy(document["analysis"]), copy.deepcopy(parent.get("evidence_sources", [])),
            copy.deepcopy(parent["decisions"]), budget, False, stop_before_generation)
    except CapturedWithoutGeneration:
        pass
    else:
        raise AssertionError("Capture must stop before any generated brief exists")
    assert captured["role"] == "role_2_creative_redactor"
    messages = runner.build_messages(captured["role"], captured["payload"], {})
    assert json.loads(messages[1]["content"])["payload"] == captured["payload"]
    return {**captured, "messages": messages,
            "metadata": {"function_executed": "llm_role_2_creative_redactor", "messages_builder_executed": "guarded_qwen_runner.build_messages",
                         "role1_inference": False, "supplied_analysis": document["analysis"],
                         "historical_cultural_context_only": True, "new_Qloo_calls": 0,
                         "model_client_created": False, "model_calls": 0, "creative_output": None,
                         "in_memory_application_callback_counter": budget["llm_calls_used"],
                         "counter_scope": "Application increments before invoking callback; this is a capture exception, not an actual model call or persistent quota."}}


def diff_paths(a, b, path=""):
    if type(a) is not type(b):
        return [path]
    if isinstance(a, dict):
        return [p for key in sorted(a.keys() | b.keys()) for p in
                (diff_paths(a[key], b[key], path + "/" + key) if key in a and key in b else [path + "/" + key])]
    if isinstance(a, list):
        if len(a) != len(b):
            return [path]
        return [p for i, (left, right) in enumerate(zip(a, b)) for p in diff_paths(left, right, path + "/" + str(i))]
    return [] if a == b else [path]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.out.resolve().is_relative_to(root):
        raise ValueError("Keep historical provider-derived fields outside the source checkout")
    assert sha(args.baseline.read_bytes()) == BASELINE_HASH
    assert sha(args.parent.read_bytes()) == PARENT_HASH
    parent = json.loads(args.parent.read_bytes())
    case_path = Path(__file__).with_name("scaffold_cases.json")
    cases = json.loads(case_path.read_bytes())
    baseline = load("scaffold_baseline", args.baseline)
    current_path = root / "taste-matched-trailer/cultural_launch_director.py"
    candidate = load("scaffold_candidate", current_path)
    runner_path = root / "taste-matched-trailer/guarded_qwen_runner.py"
    runner = load("scaffold_runner", runner_path)
    args.out.mkdir(parents=True, exist_ok=True)
    inventory = []
    for case in cases["cases"]:
        captures = {}
        for variant, director in [("old", baseline), ("candidate", candidate)]:
            result = capture(director, runner, case, cases, parent)
            filename = case["id"] + "--" + variant + ".json"
            data = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
            (args.out / filename).write_bytes(data)
            prompt = ENVELOPE + "\n\nSYSTEM\n" + result["messages"][0]["content"] + "\nEND_SYSTEM\n\nUSER\n" + result["messages"][1]["content"] + "\nEND_USER\n"
            prompt_name = case["id"] + "--" + variant + ".PROMPT.txt"
            (args.out / prompt_name).write_text(prompt)
            inventory.append({"case": case["id"], "variant": variant, "file": filename,
                              "sha256": sha(data), "messages_sha256": sha(canonical(result["messages"]).encode()),
                              "message_bytes": len(canonical(result["messages"]).encode()),
                              "prompt_file": prompt_name, "prompt_sha256": sha(prompt.encode()),
                              "prompt_bytes": len(prompt.encode()),
                              "system_content_sha256": sha(result["messages"][0]["content"].encode()),
                              "user_content_sha256": sha(result["messages"][1]["content"].encode()),
                              "director_version": director.DIRECTOR_VERSION})
            captures[variant] = result
        assert captures["old"]["messages"][0] == captures["candidate"]["messages"][0]
        paths = diff_paths(captures["old"]["payload"], captures["candidate"]["payload"])
        assert paths == ["/shot_plan/1/purpose"], paths
    receipt = {"status": "REAL_PRODUCT_FUNCTION_INPUT_CAPTURED_NO_GENERATION", "sources": {
        "baseline_director": BASELINE_HASH, "candidate_director": sha(current_path.read_bytes()),
        "runner_unchanged": sha(runner_path.read_bytes()), "cases": sha(case_path.read_bytes()), "parent": PARENT_HASH},
        "per_pair_only_payload_difference": "/shot_plan/1/purpose", "system_messages_identical": True,
        "output_schema": "native directions + four shot_overrides; not the earlier author_decision/12-word/500-word pilot",
        "native_output_cap_tokens": runner.ROLE_OUTPUT_CAPS["role_2_creative_redactor"],
        "common_envelope_sha256": sha(ENVELOPE.encode()), "capture_tool_sha256": sha(Path(__file__).read_bytes()),
        "generation_status": "NOT_REQUESTED_PENDING_ROOT_ARBITRATION", "new_Qloo_calls": 0, "new_model_calls": 0,
        "tokenizer_or_native_client_used": False, "public_ledger_mutated": False, "captures": inventory}
    (args.out / "CAPTURE-RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    def offline_only(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
            raise RuntimeError("Input capture forbids network, clients and subprocesses")
    sys.dont_write_bytecode = True
    sys.addaudithook(offline_only)
    main()
