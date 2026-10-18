#!/usr/bin/env python3
"""Verification suite for `taste_matched_trailer_agent.py` (Codex review ref: mc_6b2c9eb7d5f098100fc46e42 v2).

Proves that:
1. Offline mode (`api_key=None`) explicitly reports `qloo_api_verified=False` and `mode="offline_precomputed_demo"`,
   without claiming live pipeline `steps_completed`.
2. Invalid / unreachable API calls report `qloo_api_verified=False` and `mode="live_qloo_api_failed_fallback_to_demo"`,
   or raise `RuntimeError` when `strict_live=True`.
3. Live Qloo API responses genuinely determine `qloo_seed_books`, `qloo_cross_domain_graph`
   (`films_and_visual_aesthetic`, `soundtrack_and_composers`, `audience_personas`), and `trailer_shots`
   (`qloo_anchor`, `sonic_cue`, `visual_prompt`, `qloo_source_entity_ids`). Two distinct API payloads produce
   two measurably distinct outputs.
"""
from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import Any

from taste_matched_trailer_agent import PRECOMPUTED_PROFILES, run_agent


def _make_mock_qloo_transport(cohort: str):
    """Creates a deterministic mock Qloo API HTTP transport for Cohort A vs Cohort B."""

    def _transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
        assert headers.get("X-Api-Key"), "Missing X-Api-Key header"
        if "/search" in url and "urn%3Aentity%3Abook" in url:
            if cohort == "alpha":
                return {
                    "results": {
                        "entities": [
                            {
                                "name": " Solaris (Stanisław Lem)",
                                "entity_id": "urn:entity:book:solaris_lem",
                                "query": {"affinity": 0.97},
                            }
                        ]
                    }
                }
            return {
                "results": {
                    "entities": [
                        {
                            "name": "The Book of the New Sun (Gene Wolfe)",
                            "entity_id": "urn:entity:book:book_new_sun_wolfe",
                            "query": {"affinity": 0.84},
                        }
                    ]
                }
            }

        if ("/v2/insights" in url or "/insights" in url) and "urn%3Aentity%3Amovie" in url:
            if cohort == "alpha":
                return {
                    "results": {
                        "entities": [
                            {
                                "name": "Stalker (Andrei Tarkovsky, 1979)",
                                "entity_id": "urn:entity:movie:stalker_1979",
                                "query": {"affinity": 0.98},
                                "tags": [{"name": "Philosophical Sci-Fi"}, {"name": "Slow Cinema"}],
                            },
                            {
                                "name": "Arrival (Denis Villeneuve, 2016)",
                                "entity_id": "urn:entity:movie:arrival_2016",
                                "query": {"affinity": 0.93},
                                "tags": [{"name": "Linguistic SF"}, {"name": "Monolithic Framing"}],
                            },
                            {
                                "name": "Solaris (Andrei Tarkovsky, 1972)",
                                "entity_id": "urn:entity:movie:solaris_1972",
                                "query": {"affinity": 0.90},
                                "tags": [{"name": "Orbital Memory"}],
                            },
                        ]
                    }
                }
            return {
                "results": {
                    "entities": [
                        {
                            "name": "Gladiator (Ridley Scott, 2000)",
                            "entity_id": "urn:entity:movie:gladiator_2000",
                            "query": {"affinity": 0.88},
                            "tags": [{"name": "Roman Antiquity"}, {"name": "Imperial Legion"}],
                        },
                        {
                            "name": "The Northman (Robert Eggers, 2022)",
                            "entity_id": "urn:entity:movie:the_northman_2022",
                            "query": {"affinity": 0.85},
                            "tags": [{"name": "Ritual Oath"}, {"name": "Volcanic Ash"}],
                        },
                        {
                            "name": "Prometheus (Ridley Scott, 2012)",
                            "entity_id": "urn:entity:movie:prometheus_2012",
                            "query": {"affinity": 0.81},
                            "tags": [{"name": "Ancient Astronauts"}],
                        },
                    ]
                }
            }

        if ("/v2/insights" in url or "/insights" in url) and "urn%3Aentity%3Aartist" in url:
            if cohort == "alpha":
                return {
                    "results": {
                        "entities": [
                            {
                                "name": "Eduard Artemyev",
                                "entity_id": "urn:entity:artist:eduard_artemyev",
                                "query": {"affinity": 0.96},
                                "tags": [{"name": "Ambient Synth"}, {"name": "Organ Drone"}],
                            },
                            {
                                "name": "György Ligeti",
                                "entity_id": "urn:entity:artist:gyorgy_ligeti",
                                "query": {"affinity": 0.91},
                                "tags": [{"name": "Micropolyphony"}],
                            },
                            {
                                "name": "Arvo Pärt",
                                "entity_id": "urn:entity:artist:arvo_part",
                                "query": {"affinity": 0.89},
                                "tags": [{"name": "Tintinnabuli"}],
                            },
                        ]
                    }
                }
            return {
                "results": {
                    "entities": [
                        {
                            "name": "Hans Zimmer",
                            "entity_id": "urn:entity:artist:hans_zimmer",
                            "query": {"affinity": 0.94},
                            "tags": [{"name": "Epic Brass"}, {"name": "Ostinato"}],
                        },
                        {
                            "name": "Lisa Gerrard",
                            "entity_id": "urn:entity:artist:lisa_gerrard",
                            "query": {"affinity": 0.90},
                            "tags": [{"name": "Vocal Lament"}],
                        },
                        {
                            "name": "Vangelis",
                            "entity_id": "urn:entity:artist:vangelis",
                            "query": {"affinity": 0.87},
                            "tags": [{"name": "Mythic Synthesizer"}],
                        },
                    ]
                }
            }

        return {"results": {"entities": []}}

    return _transport


class TasteMatchedTrailerAgentTests(unittest.TestCase):
    def test_offline_demo_mode_is_explicitly_unverified(self) -> None:
        res = run_agent("le-bronze-et-la-cendre", api_key=None)
        exec_meta = res["agent_execution"]
        self.assertEqual(exec_meta["mode"], "offline_precomputed_demo")
        self.assertFalse(exec_meta["qloo_api_verified"])
        self.assertEqual(exec_meta["data_provenance"], "precomputed_reference_fixture")
        self.assertEqual(exec_meta["steps_completed"], ["offline_fixture_loaded"])
        for shot in res["trailer_shots"]:
            self.assertFalse(shot["qloo_live_derived"])

    def test_failed_api_call_does_not_claim_verified(self) -> None:
        def _failing_transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
            raise urllib.error.HTTPError(url, 401, "Unauthorized", hdrs=None, fp=None)

        res = run_agent("le-horla-maupassant", api_key="invalid-key", http_get_json=_failing_transport)
        exec_meta = res["agent_execution"]
        self.assertEqual(exec_meta["mode"], "live_qloo_api_failed_fallback_to_demo")
        self.assertFalse(exec_meta["qloo_api_verified"])
        self.assertEqual(exec_meta["data_provenance"], "precomputed_reference_fixture_after_api_error")
        self.assertTrue(len(exec_meta["api_errors"]) > 0)

        with self.assertRaises(RuntimeError):
            run_agent(
                "le-horla-maupassant",
                api_key="invalid-key",
                http_get_json=_failing_transport,
                strict_live=True,
            )

    def test_live_api_responses_genuinely_determine_scores_and_brief(self) -> None:
        offline = run_agent("le-bronze-et-la-cendre", api_key=None)
        live_alpha = run_agent(
            "le-bronze-et-la-cendre",
            api_key="test-qloo-key-alpha",
            http_get_json=_make_mock_qloo_transport("alpha"),
            strict_live=True,
        )
        live_beta = run_agent(
            "le-bronze-et-la-cendre",
            api_key="test-qloo-key-beta",
            http_get_json=_make_mock_qloo_transport("beta"),
            strict_live=True,
        )

        # Both live runs must be verified with distinct API response digests
        self.assertTrue(live_alpha["agent_execution"]["qloo_api_verified"])
        self.assertTrue(live_beta["agent_execution"]["qloo_api_verified"])
        self.assertEqual(live_alpha["agent_execution"]["mode"], "live_qloo_api_verified")
        self.assertNotEqual(
            live_alpha["agent_execution"]["live_api_response_sha256"],
            live_beta["agent_execution"]["live_api_response_sha256"],
        )

        # Seed books must differ from offline fixture and between Alpha and Beta
        self.assertNotEqual(live_alpha["qloo_seed_books"], offline["qloo_seed_books"])
        self.assertNotEqual(live_alpha["qloo_seed_books"], live_beta["qloo_seed_books"])
        self.assertEqual(live_alpha["qloo_seed_books"][0]["entity_id"], "urn:entity:book:solaris_lem")
        self.assertEqual(live_beta["qloo_seed_books"][0]["entity_id"], "urn:entity:book:book_new_sun_wolfe")

        # Cross-domain films & affinity scores must be determined by the API response
        films_alpha = live_alpha["qloo_cross_domain_graph"]["films_and_visual_aesthetic"]
        films_beta = live_beta["qloo_cross_domain_graph"]["films_and_visual_aesthetic"]
        self.assertEqual(films_alpha[0]["name"], "Stalker (Andrei Tarkovsky, 1979)")
        self.assertEqual(films_alpha[0]["affinity_score"], 0.98)
        self.assertEqual(films_beta[0]["name"], "Gladiator (Ridley Scott, 2000)")
        self.assertEqual(films_beta[0]["affinity_score"], 0.88)

        # Cross-domain composers must be determined by the API response
        comp_alpha = live_alpha["qloo_cross_domain_graph"]["soundtrack_and_composers"]
        comp_beta = live_beta["qloo_cross_domain_graph"]["soundtrack_and_composers"]
        self.assertEqual(comp_alpha[0]["name"], "Eduard Artemyev")
        self.assertEqual(comp_beta[0]["name"], "Hans Zimmer")

        # Audience personas must NOT fabricate share_pct when Qloo only returns entity affinities
        personas_alpha = live_alpha["qloo_cross_domain_graph"]["audience_personas"]
        personas_beta = live_beta["qloo_cross_domain_graph"]["audience_personas"]
        for p_item in personas_alpha + personas_beta:
            self.assertIsNone(p_item["share_pct"])
            self.assertEqual(p_item["share_pct_provenance"], "not_provided_by_qloo_api")
        self.assertEqual(personas_alpha[0]["qloo_affinity"], 0.97)
        self.assertEqual(personas_beta[0]["qloo_affinity"], 0.84)
        self.assertNotEqual(personas_alpha, personas_beta)
        self.assertNotEqual(personas_alpha, offline["qloo_cross_domain_graph"]["audience_personas"])

        # Trailer shot briefs (qloo_anchor, sonic_cue, visual_prompt) must be dynamically rewritten
        shots_alpha = live_alpha["trailer_shots"]
        shots_beta = live_beta["trailer_shots"]
        for s_off, s_a, s_b in zip(offline["trailer_shots"], shots_alpha, shots_beta):
            self.assertTrue(s_a["qloo_live_derived"])
            self.assertTrue(s_b["qloo_live_derived"])
            self.assertNotEqual(s_a["qloo_anchor"], s_off["qloo_anchor"])
            self.assertNotEqual(s_a["qloo_anchor"], s_b["qloo_anchor"])
            self.assertNotEqual(s_a["sonic_cue"], s_b["sonic_cue"])
            self.assertNotEqual(s_a["visual_prompt"], s_b["visual_prompt"])
            self.assertTrue(len(s_a["qloo_source_entity_ids"]) >= 2)

    def test_no_score_clamping_and_no_rank_fallback_when_score_missing(self) -> None:
        def _unclamped_and_unrated_transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
            if "/search" in url and "urn%3Aentity%3Abook" in url:
                return {
                    "results": {
                        "entities": [
                            {
                                "name": "Unrated Seed Book",
                                "entity_id": "urn:entity:book:unrated_seed",
                            }
                        ]
                    }
                }
            if "urn%3Aentity%3Amovie" in url:
                return {
                    "results": {
                        "entities": [
                            {
                                "name": "Low Affinity Film",
                                "entity_id": "urn:entity:movie:low_aff",
                                "query": {"affinity": 0.12},
                            },
                            {
                                "name": "Ultra High Affinity Film",
                                "entity_id": "urn:entity:movie:high_aff",
                                "query": {"affinity": 0.9991},
                            },
                        ]
                    }
                }
            if "urn%3Aentity%3Aartist" in url:
                return {
                    "results": {
                        "entities": [
                            {
                                "name": "Popularity Only Composer",
                                "entity_id": "urn:entity:artist:high_pop",
                                "popularity": 0.9991,
                            }
                        ]
                    }
                }
            return {"results": {"entities": []}}

        res = run_agent(
            "le-bronze-et-la-cendre",
            api_key="test-key-verbatim",
            http_get_json=_unclamped_and_unrated_transport,
            strict_live=True,
        )
        # Missing score must remain None, never replaced by rank fallback
        self.assertIsNone(res["qloo_seed_books"][0]["match"])
        self.assertEqual(res["qloo_seed_books"][0]["score_field_source"], "missing_in_qloo_payload")

        # 0.12 must remain 0.12 (not clamped to 0.50) and 0.9991 must remain 0.9991 (not clamped to 0.99)
        film0 = res["qloo_cross_domain_graph"]["films_and_visual_aesthetic"][0]
        film1 = res["qloo_cross_domain_graph"]["films_and_visual_aesthetic"][1]
        self.assertEqual(film0["affinity_score"], 0.12)
        self.assertEqual(film0["score_field_source"], "query.affinity")
        self.assertEqual(film1["affinity_score"], 0.9991)
        self.assertEqual(film1["score_field_source"], "query.affinity")

        # Popularity must NEVER be used as affinity_score
        comp0 = res["qloo_cross_domain_graph"]["soundtrack_and_composers"][0]
        self.assertIsNone(comp0["affinity_score"])
        self.assertEqual(comp0["score_field_source"], "missing_in_qloo_payload")

    def test_search_only_and_missing_ids_are_rejected_in_strict_live(self) -> None:
        def _search_only_transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
            if "/v2/insights" in url or "/insights" in url:
                return {"results": {"entities": []}}
            return {
                "results": {
                    "entities": [
                        {"name": "Search Discovery Only", "entity_id": "urn:entity:item:1", "query": {"affinity": 0.5}}
                    ]
                }
            }

        with self.assertRaises(RuntimeError):
            run_agent("le-bronze-et-la-cendre", api_key="test-key", http_get_json=_search_only_transport, strict_live=True)

        fallback_res = run_agent("le-bronze-et-la-cendre", api_key="test-key", http_get_json=_search_only_transport, strict_live=False)
        self.assertFalse(fallback_res["agent_execution"]["qloo_api_verified"])

        def _missing_id_transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
            return {"results": {"entities": [{"name": "Entity Without ID", "query": {"affinity": 0.8}}]}}

        with self.assertRaises(RuntimeError):
            run_agent("le-bronze-et-la-cendre", api_key="test-key", http_get_json=_missing_id_transport, strict_live=True)

    def test_export_ltx_brief_includes_provenance_and_live_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            brief_path = Path(tmpdir) / "brief.json"
            run_agent(
                "le-bronze-et-la-cendre",
                api_key="test-qloo-key-alpha",
                export_ltx_brief=brief_path,
                http_get_json=_make_mock_qloo_transport("alpha"),
                strict_live=True,
            )
            payload = json.loads(brief_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["qloo_api_verified"])
            self.assertEqual(payload["data_provenance"], "qloo_live_api_responses")
            self.assertTrue(payload["shots"][0]["qloo_live_derived"])
            self.assertIn("Stalker", payload["shots"][0]["qloo_anchor"])
            self.assertIn("Eduard Artemyev", payload["shots"][0]["sonic_cue"])


if __name__ == "__main__":
    unittest.main()
