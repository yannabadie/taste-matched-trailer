"""Portable synthetic tests for Director 2.6.3; no recorded response is loaded.

All scenes, briefs and simulated verifier observations below are invented for
unit tests. They prove neither Qloo authenticity nor native model behavior.
Run beside cultural_launch_director.py and guarded_qwen_runner.py:
    python3 -B test_semantic_contract_synthetic.py
"""
from pathlib import Path
import copy
import importlib.util
import json
import sys
import unittest

sys.dont_write_bytecode = True


def offline_only(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("Synthetic semantic tests prohibit network and subprocesses")


sys.addaudithook(offline_only)
HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load("cultural_launch_director")
runner = load("guarded_qwen_runner")


def synthetic_brief():
    return {
        "id": "synthetic-semantic-brief",
        "run_id": "synthetic-semantic-test",
        "mode": "fixture",
        "qloo_api_verified": False,
        "synopsis": "An inventor notices ordinary objects changing position.",
        "user_constraints": {
            "duration_seconds": 40,
            "aspect_ratio": "16:9",
            "no_visible_monster": True,
        },
        "completeness": "complete",
        "decision_refs": [],
        "shots": [
            {
                "id": f"shot_{i:02d}",
                "duration_seconds": 10,
                "aspect_ratio": "16:9",
                "visual_prompt": "A pencil rolls across an empty desk in steady daylight.",
                "on_screen_text": "Where did it begin?",
                "voiceover": "",
                "sonic_direction": "",
                "decision_refs": [],
                "evidence_refs": [],
                "retained_entity_refs": [],
                "interpretation_labels": ["user_constraint", "editorial_inference", "synthetic_fixture"],
            }
            for i in range(1, 5)
        ],
    }


def budget():
    return core.make_initial_run_budget("synthetic-semantic-test", 0, 3)


def errors(brief):
    return core.validate_contract_links(brief, [], [], budget())


class SyntheticSemanticContract(unittest.TestCase):
    def test_editorial_shots_need_no_invented_lineage(self):
        self.assertEqual(errors(synthetic_brief()), [])

    def test_qloo_claim_without_links_is_rejected_at_every_position(self):
        for index in range(4):
            with self.subTest(index=index):
                brief = synthetic_brief()
                brief["shots"][index]["interpretation_labels"] = ["qloo_result"]
                self.assertTrue(any("without both evidence_refs and decision_refs" in e for e in errors(brief)))

    def test_fixture_cannot_become_api_verified(self):
        brief = synthetic_brief()
        brief["qloo_api_verified"] = True
        found = errors(brief)
        self.assertTrue(any("fixture mode" in e for e in found))
        self.assertTrue(any("at least one shot attributed" in e for e in found))

    def test_visible_phenomenon_forms_are_refused_fr_en(self):
        for visual in [
            "Une forme humanoïde se dessine derrière la porte.",
            "A spectral outline forms beside the staircase.",
            "A shadowy figure emerges behind an empty chair.",
            "The narrator's face is visible while a humanoid figure emerges behind them.",
        ]:
            with self.subTest(visual=visual):
                brief = synthetic_brief()
                brief["shots"][1]["visual_prompt"] = visual
                self.assertTrue(any("visible apparition shape" in e for e in errors(brief)))

    def test_narrator_object_traces_and_negations_remain_permitted(self):
        for visual in [
            "The narrator's ordinary face looks down at a motionless pencil.",
            "Le visage du narrateur regarde une lettre sur le bureau.",
            "The ordinary shadow of a pencil moves across the desk.",
            "Un bureau vide, sans silhouette ni contour humanoïde.",
            "An empty desk, no silhouette or humanoid outline.",
        ]:
            with self.subTest(visual=visual):
                brief = synthetic_brief()
                brief["shots"][0]["visual_prompt"] = visual
                self.assertEqual(errors(brief), [])

    def test_objects_and_typography_still_forbid_a_narrator_face(self):
        brief = synthetic_brief()
        brief["user_constraints"]["assets"] = ["objects", "typography"]
        for shot in brief["shots"]:
            shot["assets"] = ["objects", "typography"]
        brief["shots"][0]["visual_prompt"] = "The narrator's face looks down at a letter."
        self.assertTrue(any("visible person" in e for e in errors(brief)))

    def test_fake_accept_cannot_override_a_deterministic_violation(self):
        brief = synthetic_brief()
        brief["shots"][0]["visual_prompt"] = "A humanoid outline stands behind the desk."
        fake = lambda role, payload: {"llm_status": "accept", "unresolved_claims": []}
        result = core.llm_role_3_verifier(brief, [], [], budget(), fake)
        self.assertEqual(result["llm_status"], "block")

    def test_simulated_revise_and_block_observations_are_preserved(self):
        for verdict in ("revise", "block"):
            with self.subTest(verdict=verdict):
                fake = lambda role, payload: {"llm_status": verdict, "unresolved_claims": ["Synthetic unresolved observation"]}
                result = core.llm_role_3_verifier(synthetic_brief(), [], [], budget(), fake)
                self.assertEqual(result["llm_status"], verdict)
                self.assertEqual(result["unresolved_claims"], ["Synthetic unresolved observation"])

    def test_duration_sound_off_and_budget_controls_still_apply(self):
        brief = synthetic_brief()
        brief["shots"][0]["duration_seconds"] += 1
        self.assertTrue(any("durations" in e for e in errors(brief)))
        brief = synthetic_brief()
        brief["user_constraints"]["sound_off"] = True
        brief["shots"][0]["voiceover"] = "A test line."
        self.assertTrue(any("sound_off" in e for e in errors(brief)))
        used = budget()
        used["llm_calls_used"] = used["llm_call_limit"] + 1
        self.assertTrue(any("exceeds limit" in e for e in core.validate_contract_links(synthetic_brief(), [], [], used)))

    def test_prompts_follow_requested_language_and_general_editorial_rule(self):
        writer = runner.build_messages("role_2_creative_redactor", {"synopsis": "A quiet study.", "user_constraints": {"language": "en"}})
        self.assertNotIn("French scenes", writer[0]["content"])
        self.assertIn("otherwise use the synopsis language", writer[0]["content"])
        self.assertIn("strictly invisible", writer[0]["content"])
        self.assertEqual(json.loads(writer[1]["content"])["payload"]["user_constraints"]["language"], "en")
        brief = synthetic_brief()
        context = {"brief": brief, "decisions": [], "evidences": [], "user_constraints": copy.deepcopy(brief["user_constraints"])}
        verifier = runner.build_messages("role_3_verifier", {}, context)
        for text in ("per shot, not by shot number", "qloo_result claim requires", "may legitimately have empty", "accept only if no unresolved claim"):
            self.assertIn(text, verifier[0]["content"])

    def test_output_caps_and_field_bounds_remain_explicit(self):
        self.assertEqual(runner.ROLE_OUTPUT_CAPS, {"role_1_brief_analyst": 450, "role_2_creative_redactor": 1200, "role_3_verifier": 300})
        fields = {"visual_prompt": "A desk.", "voiceover": "", "sonic_direction": "", "on_screen_text": "Read."}
        output = {"directions": [{"title": "Stillness", "angle": "Watch the changing objects."}], "shot_overrides": {f"shot_{i:02d}": copy.deepcopy(fields) for i in range(1, 5)}}
        output["shot_overrides"]["shot_01"]["visual_prompt"] = "x" * 241
        with self.assertRaises(runner.AdapterContractError):
            runner.validate_role_output("role_2_creative_redactor", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
