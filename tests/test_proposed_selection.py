"""Synthetic selection contracts; no network, native model or recorded Qloo response."""
from pathlib import Path
import copy
import importlib.util
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True


def offline_only(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("Selection tests prohibit network and subprocesses")


sys.addaudithook(offline_only)
SOURCE = Path(__file__).resolve().parents[1] / "taste-matched-trailer/cultural_launch_director.py"
spec = importlib.util.spec_from_file_location("proposal_selection_core", SOURCE)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def evidence():
    return core.build_evidence_from_envelope(
        "synthetic-evidence", "run-synthetic-selection", "fixture", "qloo_recommend",
        {"target_type": "movie", "signals": ["synthetic-book"], "limit": 6}, ["synthetic-book"],
        {"status": "ok", "mode": "fixture", "results": [
            {"entity_id": "synthetic-a", "name": "Synthetic A", "type": "urn:entity:movie", "affinity": .2},
            {"entity_id": "synthetic-b", "name": "Synthetic B", "type": "urn:entity:movie", "affinity": .9},
            {"entity_id": "synthetic-c", "name": "Synthetic C", "type": "urn:entity:movie", "affinity": .6},
        ]}, "2026-10-27T12:00:00Z", "2026-10-27T12:00:01Z")


def choose(selected, source=None):
    return core.select_from_valid_results(
        "synthetic-decision", "run-synthetic-selection", "choose_proposed_movies",
        source or evidence(), "urn:entity:movie", [], explicit_selected_ids=selected)


def render_fixture(decision, source, calls):
    validated = core.validate_brief("A gentle book about reading indoors.", ["Synthetic public reference"],
        {"duration_seconds": 38, "aspect_ratio": "16:9", "tone": "gentle", "launch_audience_context": "synthetic test"})
    def fake_writer(role, payload):
        calls.append(role)
        return {"directions": [], "shot_overrides": {f"shot_{i:02d}": {
            "visual_prompt": "A quiet reading table.", "voiceover": "", "sonic_direction": "", "on_screen_text": "Read the page."
        } for i in range(1, 5)}}
    budget = core.make_initial_run_budget("run-synthetic-selection", 0, 3)
    brief, _ = core.llm_role_2_creative_redactor("run-synthetic-selection", "fixture", validated, {"themes": []},
        [source], [decision], budget, False, fake_writer)
    return brief, budget


class ProposedSelection(unittest.TestCase):
    def test_recommendation_without_explicit_choice_is_refused_by_inert_preflight(self):
        with self.assertRaises(ValueError):
            core.preflight_run_request({"synopsis": "A gentle book about reading indoors.", "rank_domains": ["movie"],
                "shortlist_options": {"movie": ["synthetic-a"]}, "insights_tool": "qloo_recommend"})

    def test_recommendation_pipeline_keeps_operation_and_explicit_choices(self):
        seed = "synthetic-book-for-recommendation"
        rows = copy.deepcopy(evidence()["payload_redacted"]["results"])
        calls = []
        def fake_model(role, payload):
            calls.append(role)
            if role == "role_1_brief_analyst":
                return {}
            if role == "role_3_verifier":
                return {"llm_status": "accept", "unresolved_claims": []}
            return {"directions": [], "shot_overrides": {f"shot_{i:02d}": {
                "visual_prompt": "A quiet reading table.", "voiceover": "", "sonic_direction": "", "on_screen_text": "Read the page."
            } for i in range(1, 5)}}
        with mock.patch.dict(core.FIXTURE_RECOMMENDATIONS_BY_SEED, {seed: {"movie": rows}}):
            result = core.run_cultural_launch_director("A gentle book about reading indoors.", ["Controlled public reference"],
                {"duration_seconds": 38, "aspect_ratio": "16:9"}, [seed], mode="fixture",
                custom_resolver=lambda _query: [{"entity_id": seed, "name": "Controlled book", "entity_type": "urn:entity:book"}],
                rank_domains=["movie"], shortlist_options={"movie": ["synthetic-c", "synthetic-a"]}, llm_runner=fake_model,
                insights_tool="qloo_recommend", explicit_selected_ids=["synthetic-c", "synthetic-a"])
        self.assertEqual(result["workflow_status"], "ok")
        self.assertEqual(result["question_plan"]["planned_steps"][0]["tool"], "qloo_recommend")
        self.assertEqual(result["evidences"][0]["tool"], "qloo_recommend")
        self.assertEqual(result["decisions"][0]["selected_entity_ids"], ["synthetic-a", "synthetic-c"])
        self.assertEqual(result["brief"]["shots"][0]["retained_entity_refs"], ["synthetic-c"])
        self.assertEqual(calls, ["role_1_brief_analyst", "role_2_creative_redactor", "role_3_verifier"])
        self.assertFalse(result["brief"]["qloo_api_verified"])
        public = core.build_public_export(result)
        self.assertEqual(public["decisions"][0]["constraints_origin"][-1]["submitted_entity_ids"], ["synthetic-c", "synthetic-a"])

    def test_recommendation_cannot_borrow_another_tool_or_foreign_acquisition(self):
        args = {"target_type": "movie", "signals": ["synthetic-book"], "limit": 6}
        for foreign in [False, True]:
            origin = "run-another-source" if foreign else "run-synthetic-selection"
            envelope = {"status": "ok", "run_id": origin, "input_hash": "a" * 64,
                "authentication_state": "authenticated", "source_payload_sha256": "b" * 64,
                "results": copy.deepcopy(evidence()["payload_redacted"]["results"]),
                "tool_call_provenance": {"tool": "qloo_recommend" if foreign else "qloo_rank", "arguments": args,
                    "run_id": origin, "input_hash": "a" * 64, "source_payload_sha256": "b" * 64}}
            result = core.build_evidence_from_envelope("synthetic-evidence", "run-synthetic-selection", "live", "qloo_recommend",
                args, ["synthetic-book"], envelope, "2026-10-27T12:00:00Z", "2026-10-27T12:00:01Z", expected_input_hash="a" * 64)
            self.assertNotEqual(result["authentication_state"], "authenticated")

    def test_explicit_choice_preserves_api_order_and_records_author_order_separately(self):
        source = evidence()
        before = copy.deepcopy(source)
        result = choose(["synthetic-c", "synthetic-a"], source)
        self.assertEqual(result["selected_entity_ids"], ["synthetic-a", "synthetic-c"])
        self.assertEqual([x["qualification_state"] for x in result["candidates"]], ["retenu", "écarté", "retenu"])
        self.assertEqual([x["returned_order"] for x in result["candidates"]], [0, 1, 2])
        self.assertEqual(result["constraints_origin"][-1]["submitted_entity_ids"], ["synthetic-c", "synthetic-a"])
        self.assertEqual(source, before)
        self.assertEqual(result["claim_origin"], "editorial_inference")

    def test_empty_duplicate_and_unsupplied_choices_are_refused(self):
        for selected in [[], ["synthetic-a", "synthetic-a"], ["not-supplied"], ["synthetic-a", "synthetic-b", "synthetic-c", "fourth"]]:
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                choose(selected)

    def test_old_automatic_selection_is_unchanged_without_explicit_choice(self):
        result = core.select_from_valid_results("synthetic-decision", "run-synthetic-selection", "legacy_selection", evidence(), "urn:entity:movie", [])
        self.assertEqual(result["selected_entity_ids"], ["synthetic-a", "synthetic-b"])

    def test_writer_source_reference_is_resolved_by_id_even_when_two_lists_have_different_orders(self):
        source = evidence()
        decision = choose(["synthetic-c", "synthetic-a"], source)
        decision["selected_entity_ids"] = ["synthetic-c", "synthetic-a"]
        brief, _ = render_fixture(decision, source, [])
        first = brief["shots"][0]
        self.assertEqual(first["retained_entity_refs"], ["synthetic-c"])
        target = core.resolve_json_pointer(source["payload_redacted"], first["evidence_refs"][0]["item_pointer"])
        self.assertEqual(target["entity_id"], "synthetic-c")

    def test_validator_refuses_a_shot_citing_another_globally_retained_reference(self):
        source = evidence()
        decision = choose(["synthetic-a", "synthetic-c"], source)
        brief, budget = render_fixture(decision, source, [])
        brief["shots"][0]["evidence_refs"] = [{"evidence_id": source["id"], "item_pointer": "/results/2"}]
        found = core.validate_contract_links(brief, [decision], [source], budget)
        self.assertTrue(any("retained_entity_refs" in message for message in found), found)

    def test_nonselected_source_in_a_decision_is_refused_before_the_writer_runs(self):
        source = evidence()
        decision = choose(["synthetic-a", "synthetic-c"], source)
        decision["evidence_refs"][0]["item_pointer"] = "/results/1"
        calls = []
        with self.assertRaises(ValueError):
            render_fixture(decision, source, calls)
        self.assertEqual(calls, [])

    def test_corrupt_source_is_refused_before_even_the_analyst_model(self):
        seed = "synthetic-book-for-binding-check"
        rows = copy.deepcopy(evidence()["payload_redacted"]["results"])
        original = core.select_from_valid_results
        def corrupt(*args, **kwargs):
            decision = original(*args, **kwargs)
            self.assertGreaterEqual(len(decision["evidence_refs"]), 2)
            decision["evidence_refs"][0] = copy.deepcopy(decision["evidence_refs"][1])
            return decision
        calls = []
        def model_must_not_run(role, payload):
            calls.append(role)
            raise RuntimeError("The model must not run")
        with mock.patch.dict(core.FIXTURE_RECOMMENDATIONS_BY_SEED, {seed: {"movie": rows}}), mock.patch.object(core, "select_from_valid_results", corrupt):
            result = core.run_cultural_launch_director("A gentle book about reading indoors.", ["Controlled public reference"],
                {"duration_seconds": 38, "aspect_ratio": "16:9"}, [seed], mode="fixture",
                custom_resolver=lambda _query: [{"entity_id": seed, "name": "Controlled book", "entity_type": "urn:entity:book"}],
                rank_domains=["movie"], shortlist_options={"movie": [row["entity_id"] for row in rows]}, llm_runner=model_must_not_run)
        self.assertEqual(result["workflow_status"], "invalid_contract")
        self.assertEqual(result["run_budget"]["llm_calls_used"], 0)
        self.assertEqual(calls, [])

    def test_exhausted_family_time_returns_without_resolution_or_model(self):
        def must_not_run(*_args):
            self.fail("No work may start after the active family budget")
        result = core.run_cultural_launch_director("A gentle book about reading indoors.", ["Controlled public reference"],
            {}, mode="fixture", custom_resolver=must_not_run, llm_runner=must_not_run,
            active_time_limit_ms=120000, active_time_already_used_ms=120000)
        self.assertEqual(result["workflow_status"], "error")
        self.assertEqual(result["run_budget"]["llm_calls_used"], 0)


if __name__ == "__main__":
    unittest.main()
