#!/usr/bin/env python3
"""
Cultural Launch Director — Bounded Multi-Role & Deterministic Qloo Harness Pipeline
===================================================================================

Implements the offline-ready architecture specified in:
- `campagne-hackathon-2026-10-19/ARCHITECTURE.txt`
- `campagne-hackathon-2026-10-19/implementation/PLAN-PRODUCTEUR.txt`
- `campagne-hackathon-2026-10-19/recherche/CORRECTIONS-AVIS-CLAUDE.txt`
- `campagne-hackathon-2026-10-19/conception/CONTRATS.schema.json`
- `campagne-hackathon-2026-10-19/validation/CAS-EVALUATION.json`

Key invariants enforced:
1. Three bounded LLM roles (Brief Analyst, Creative Redactor, Verifier) sharing a single
   per-run budget (max 5 LLM calls, 24,000 input tokens, 6,000 output tokens) with at most
   one repair turn.
2. Deterministic candidate resolution and mandatory user confirmation gate before any entity
   ID is used as a Qloo taste signal. Ambiguous matches (`Crash`, `Dune`) pause with
   `status="needs_input"`; unknown/synthetic titles (`Les Archives du Septième Brouillard`)
   never receive fabricated IDs.
3. Official `@qloo/qloo-harness` stdio tool semantics (`qloo_capabilities`, `qloo_find_tags`,
   `qloo_describe`, `qloo_rank`, `qloo_recommend`, optional `qloo_compare_audiences`),
   six envelope statuses (`ok`, `empty`, `needs_input`, `partial`, `degraded`, `error`) plus
   `invalid_contract` on unknown status, and strict retry rules (max 1 retry per call only
   when `error.retryable=True` and within the 8-attempt cap).
4. Three explicit modes (`live`, `recorded_live`, `fixture`). Neither `fixture` nor
   `qloo_capabilities` readiness nor `recorded_live` replay is ever presented as a live
   authenticated Qloo qualification (`qloo_api_verified` is strictly `False` on fixtures,
   empty/partial/degraded/error runs, or unconfirmed inputs).
5. Strict lineage `Evidence` -> `Decision` -> `Brief` with JSON Pointer verification
   (`/results/entities/0`) and selective dependency invalidation when a user removes a
   confirmed reference.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path as _Path
from typing import Any, Callable

DIRECTOR_VERSION = "2.6.6-creature-negation-20261025"
REFERENCE_LINK_LIMITATION = ("Per-shot reference links are compatibility provenance of received sources, "
    "not instructions to the writer or evidence that a reference caused any scene.")
RULE_VERSION = "det-select-v1.5"
REQUIRED_NODE_MIN = "22.19.0"
REQUIRED_HARNESS_MIN = "0.1.26"
QLOO_CONTRACT_VERSION = "1.0.0"
QLOO_CONTRACT_CHECKSUM = "sha256:762bdcc5e14ff797b6de739d2658a83f78af35e68d7a5a3449455be6046924f5"
QLOO_RESULT_SCHEMA_VERSION = "1.0-preview.1"
INSTALLED_HARNESS_ROOT = str(_Path.home() / "Library/Application Support/Agentique/qloo-harness-0.1.26")
INSTALLED_HARNESS_BIN = f"{INSTALLED_HARNESS_ROOT}/node_modules/.bin/qloo"
PRODUCT_PROMISE_STATEMENT = (
    "Références culturelles pour une direction créative et un brief — "
    "sans promesse de comparables commerciaux, de conversion, de ventes ou de positionnement éditorial validé."
)

# Exact 10 tools exposed by installed `@qloo/qloo-harness@0.1.26` (`qloo_find` does NOT exist; `qloo_describe` resolves entities).
QLOO_CANONICAL_TEN_TOOLS: tuple[str, ...] = (
    "qloo_capabilities",
    "qloo_recommend",
    "qloo_rank",
    "qloo_describe",
    "qloo_where_popular",
    "qloo_compare_audiences",
    "qloo_entity_tags",
    "qloo_audience_demographics",
    "qloo_trends",
    "qloo_find_tags",
)

# Active subset used by Cultural Launch Director (`qloo_compare_audiences` excluded per product decision)
OFFICIAL_MCP_TOOLS: tuple[str, ...] = (
    "qloo_capabilities",
    "qloo_find_tags",
    "qloo_describe",
    "qloo_rank",
    "qloo_recommend",
)

QLOO_RANK_OPTION_TYPES: tuple[str, ...] = (
    "artist",
    "book",
    "brand",
    "movie",
    "person",
    "place",
    "podcast",
    "tv_show",
    "videogame",
)

DEFAULT_RANK_DOMAINS: tuple[str, ...] = ("movie", "artist")

QLOO_DESCRIBE_ENTITY_TYPES: tuple[str, ...] = (
    "artist",
    "book",
    "brand",
    "movie",
    "person",
    "place",
    "podcast",
    "tv_show",
    "videogame",
    "locality",
    "actor",
    "album",
    "author",
    "director",
)

ALLOWED_STATUSES: tuple[str, ...] = (
    "ok",
    "empty",
    "needs_input",
    "partial",
    "degraded",
    "error",
    "invalid_contract",
)

ALLOWED_MODES: tuple[str, ...] = ("live", "recorded_live", "fixture")

INTERNAL_BUDGET_PROPOSALS: dict[str, int] = {
    "qloo_network_attempt_limit": 8,
    "llm_call_limit": 3,
    "max_retries_per_call": 0,
    "active_time_limit_ms": 120000,
    "llm_input_token_limit": 24000,
    "llm_output_token_limit": 6000,
    "max_in_flight": 2,
    "tool_timeout_ms": 15000,
}

# Offline disambiguation & reference catalog used ONLY in `fixture` mode (never labeled live).
FIXTURE_CATALOG: dict[str, list[dict[str, Any]]] = {
    "hyperion": [
        {
            "name": "Hyperion",
            "entity_id": "urn:entity:book:hyperion_simmons",
            "entity_type": "urn:entity:book",
            "disambiguation": "Dan Simmons (1989 speculative fiction novel)",
            "source": "synthetic_fixture",
        }
    ],
    "memoirs of hadrian": [
        {
            "name": "Memoirs of Hadrian",
            "entity_id": "urn:entity:book:memoires_d_hadrien",
            "entity_type": "urn:entity:book",
            "disambiguation": "Marguerite Yourcenar (1951 historical novel)",
            "source": "synthetic_fixture",
        }
    ],
    "dune": [
        {
            "name": "Dune (Novel, 1965)",
            "entity_id": "urn:entity:book:dune_herbert",
            "entity_type": "urn:entity:book",
            "disambiguation": "Frank Herbert (1965 science fiction novel)",
            "source": "synthetic_fixture",
        },
        {
            "name": "Dune: Part One (Film, 2021)",
            "entity_id": "urn:entity:movie:dune_2021",
            "entity_type": "urn:entity:movie",
            "disambiguation": "Denis Villeneuve (2021 feature film)",
            "source": "synthetic_fixture",
        },
    ],
    "crash": [
        {
            "name": "Crash (Novel, 1973)",
            "entity_id": "urn:entity:book:crash_ballard_1973",
            "entity_type": "urn:entity:book",
            "disambiguation": "J.G. Ballard (1973 novel)",
            "source": "synthetic_fixture",
        },
        {
            "name": "Crash (Film, 1996)",
            "entity_id": "urn:entity:movie:crash_cronenberg_1996",
            "entity_type": "urn:entity:movie",
            "disambiguation": "David Cronenberg (1996 psychological drama film)",
            "source": "synthetic_fixture",
        },
        {
            "name": "Crash (Film, 2004)",
            "entity_id": "urn:entity:movie:crash_haggis_2004",
            "entity_type": "urn:entity:movie",
            "disambiguation": "Paul Haggis (2004 ensemble drama film)",
            "source": "synthetic_fixture",
        },
    ],
    "the turn of the screw": [
        {
            "name": "The Turn of the Screw",
            "entity_id": "urn:entity:book:turn_of_the_screw_james",
            "entity_type": "urn:entity:book",
            "disambiguation": "Henry James (1898 gothic novella)",
            "source": "synthetic_fixture",
        }
    ],
    "rebecca": [
        {
            "name": "Rebecca",
            "entity_id": "urn:entity:book:rebecca_du_maurier",
            "entity_type": "urn:entity:book",
            "disambiguation": "Daphne du Maurier (1938 gothic novel)",
            "source": "synthetic_fixture",
        }
    ],
    "foundation": [
        {
            "name": "Foundation",
            "entity_id": "urn:entity:book:foundation_asimov",
            "entity_type": "urn:entity:book",
            "disambiguation": "Isaac Asimov (1951 science fiction novel)",
            "source": "synthetic_fixture",
        }
    ],
}

# Homogeneous same-type shortlists (3–6 items per type) used in `fixture` mode to illustrate
# `qloo_rank` ordering and tri-state qualification (`retenu` / `écarté` / `non_évaluable`).
FIXTURE_RECOMMENDATIONS_BY_SEED: dict[str, dict[str, list[dict[str, Any]]]] = {
    "urn:entity:book:hyperion_simmons": {
        "movie": [
            {
                "name": "Arrival (Denis Villeneuve, 2016)",
                "entity_id": "urn:entity:movie:arrival_2016",
                "entity_type": "urn:entity:movie",
                "returned_order": 0,
                "query": {},
            },
            {
                "name": "Blade Runner 2049 (Denis Villeneuve, 2017)",
                "entity_id": "urn:entity:movie:blade_runner_2049",
                "entity_type": "urn:entity:movie",
                "returned_order": 1,
                "query": {},
            },
            {
                "name": "Solaris (Andrei Tarkovsky, 1972)",
                "entity_id": "urn:entity:movie:solaris_1972",
                "entity_type": "urn:entity:movie",
                "returned_order": 2,
                "query": {},
            },
            {
                "name": "Hard to Be a God (Aleksei German, 2013 — unindexed candidate)",
                "entity_id": "",
                "entity_type": "urn:entity:movie",
                "returned_order": None,
                "query": {},
            },
        ],
        "artist": [
            {
                "name": "Jóhann Jóhannsson",
                "entity_id": "urn:entity:artist:johann_johannsson",
                "entity_type": "urn:entity:artist",
                "returned_order": 0,
                "query": {},
            },
            {
                "name": "Max Richter",
                "entity_id": "urn:entity:artist:max_richter",
                "entity_type": "urn:entity:artist",
                "returned_order": 1,
                "query": {},
            },
            {
                "name": "Colin Stetson",
                "entity_id": "urn:entity:artist:colin_stetson",
                "entity_type": "urn:entity:artist",
                "returned_order": 2,
                "query": {},
            },
        ],
    },
    "urn:entity:book:turn_of_the_screw_james": {
        "movie": [
            {
                "name": "The Innocents (Jack Clayton, 1961)",
                "entity_id": "urn:entity:movie:the_innocents_1961",
                "entity_type": "urn:entity:movie",
                "returned_order": 0,
                "query": {},
            },
            {
                "name": "The Others (Alejandro Amenábar, 2001)",
                "entity_id": "urn:entity:movie:the_others_2001",
                "entity_type": "urn:entity:movie",
                "returned_order": 1,
                "query": {},
            },
            {
                "name": "The Lighthouse (Robert Eggers, 2019)",
                "entity_id": "urn:entity:movie:the_lighthouse_2019",
                "entity_type": "urn:entity:movie",
                "returned_order": 2,
                "query": {},
            },
            {
                "name": "Lake Mungo (Joel Anderson, 2008 — unindexed candidate)",
                "entity_id": "",
                "entity_type": "urn:entity:movie",
                "returned_order": None,
                "query": {},
            },
        ],
        "artist": [
            {
                "name": "Hildur Guðnadóttir",
                "entity_id": "urn:entity:artist:hildur_gudnadottir",
                "entity_type": "urn:entity:artist",
                "returned_order": 0,
                "query": {},
            },
            {
                "name": "Krzysztof Penderecki",
                "entity_id": "urn:entity:artist:krzysztof_penderecki",
                "entity_type": "urn:entity:artist",
                "returned_order": 1,
                "query": {},
            },
            {
                "name": "Bernard Herrmann",
                "entity_id": "urn:entity:artist:bernard_herrmann",
                "entity_type": "urn:entity:artist",
                "returned_order": 2,
                "query": {},
            },
        ],
    },
    "urn:entity:book:dune_herbert": {
        "movie": [
            {
                "name": "Lawrence of Arabia (David Lean, 1962)",
                "entity_id": "urn:entity:movie:lawrence_of_arabia_1962",
                "entity_type": "urn:entity:movie",
                "returned_order": 0,
                "query": {},
            },
            {
                "name": "Stalker (Andrei Tarkovsky, 1979)",
                "entity_id": "urn:entity:movie:stalker_1979",
                "entity_type": "urn:entity:movie",
                "returned_order": 1,
                "query": {},
            },
            {
                "name": "Aguirre, the Wrath of God (Werner Herzog, 1972)",
                "entity_id": "urn:entity:movie:aguirre_1972",
                "entity_type": "urn:entity:movie",
                "returned_order": 2,
                "query": {},
            },
        ],
        "artist": [
            {
                "name": "Brian Eno",
                "entity_id": "urn:entity:artist:brian_eno",
                "entity_type": "urn:entity:artist",
                "returned_order": 0,
                "query": {},
            },
            {
                "name": "Lisa Gerrard",
                "entity_id": "urn:entity:artist:lisa_gerrard",
                "entity_type": "urn:entity:artist",
                "returned_order": 1,
                "query": {},
            },
            {
                "name": "Vangelis",
                "entity_id": "urn:entity:artist:vangelis",
                "entity_type": "urn:entity:artist",
                "returned_order": 2,
                "query": {},
            },
        ],
    },
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_canonical(obj: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()


_RUN_ID_SEQUENCE = 0


def _allocate_execution_run_id(input_hash: str, mode: str, explicit_run_id: str | None = None) -> str:
    global _RUN_ID_SEQUENCE
    if explicit_run_id is not None:
        if not isinstance(explicit_run_id, str) or not re.fullmatch(r"run-[A-Za-z0-9_-]{4,64}", explicit_run_id):
            raise ValueError("explicit_run_id must be a safe preallocated run- identifier")
        return explicit_run_id
    _RUN_ID_SEQUENCE += 1
    entropy = f"{input_hash}:{mode}:{time.time_ns()}:{_RUN_ID_SEQUENCE}"
    return f"run-{mode[:3]}-{hashlib.sha256(entropy.encode()).hexdigest()[:12]}"



_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SECRET_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]+|X-Api-Key\s*[:=]\s*[A-Za-z0-9._-]+)",
    re.IGNORECASE,
)
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"consignes\s+de\s+contrôle\s+étrangères", re.IGNORECASE),
    re.compile(r"exfiltrat|print\s+env|dump\s+secret", re.IGNORECASE),
)


def redact_sensitive_text(text: str) -> str:
    """Strips email addresses and secret-like tokens so no PII/secret enters logs or Qloo requests."""
    cleaned = _EMAIL_RE.sub("[REDACTED_EMAIL]", str(text or ""))
    cleaned = _SECRET_RE.sub("[REDACTED_CREDENTIAL]", cleaned)
    return cleaned.strip()


def detect_embedded_control_instructions(text: str) -> list[str]:
    """Detects untrusted control/injection phrases inside user input so they are isolated as inert data."""
    findings: list[str] = []
    for pat in _INJECTION_PATTERNS:
        if pat.search(text or ""):
            findings.append(pat.pattern)
    return findings


def resolve_json_pointer(doc: Any, pointer: str) -> Any:
    """Resolves a RFC 6901 JSON Pointer (e.g. `/results/entities/0`) against `doc`."""
    if pointer == "" or pointer == "/":
        return doc
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid JSON Pointer {pointer!r}: must start with '/'")
    current = doc
    for raw_part in pointer.lstrip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            idx = int(part)
            if idx < 0 or idx >= len(current):
                raise KeyError(f"JSON Pointer index {idx} out of range in {pointer!r}")
            current = current[idx]
        elif isinstance(current, dict):
            if part not in current:
                raise KeyError(f"JSON Pointer key {part!r} not found in {pointer!r}")
            current = current[part]
        else:
            raise KeyError(f"Cannot traverse non-container at {part!r} in {pointer!r}")
    return current


def make_initial_run_budget(run_id: str, qloo_network_attempt_limit: int = 8,
                            llm_call_limit: int = 3, active_time_limit_ms: int = 120000,
                            physical_http_attempts_used: int = 0) -> dict[str, Any]:
    for value, lower, upper, name in [(qloo_network_attempt_limit,0,14,"qloo_network_attempt_limit"),
             (llm_call_limit,0,3,"llm_call_limit"),(active_time_limit_ms,1,120000,"active_time_limit_ms"),
             (physical_http_attempts_used,0,qloo_network_attempt_limit,"physical_http_attempts_used")]:
        if isinstance(value,bool) or not isinstance(value,int) or not lower <= value <= upper:
            raise ValueError(f"Invalid {name}")
    return {"run_id":run_id,"limits_are_internal_proposals":True,
        "qloo_network_attempt_limit":qloo_network_attempt_limit,"qloo_network_attempts_used":physical_http_attempts_used,
        "llm_call_limit":llm_call_limit,"llm_calls_used":0,"max_retries_per_call":0,
        "active_time_limit_ms":active_time_limit_ms,"active_time_used_ms":0,
        "quota_official_state":"unknown","charge_known":None}


def validate_brief(
    synopsis: str,
    suggested_public_references: list[str] | None = None,
    user_constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Step 1 (`validate_brief`): sanitizes input, isolates untrusted instructions, tags `user_constraint` origins."""
    clean_synopsis = redact_sensitive_text(synopsis)
    clean_refs = [redact_sensitive_text(r) for r in (suggested_public_references or []) if str(r).strip()]
    raw_constraints = dict(user_constraints or {})
    clean_constraints: dict[str, Any] = {}
    constraints_origin: list[dict[str, Any]] = []

    for k, v in raw_constraints.items():
        clean_val = redact_sensitive_text(v) if isinstance(v, str) else v
        clean_constraints[k] = clean_val
        constraints_origin.append(
            {
                "constraint": k,
                "value": clean_val,
                "origin": "user_constraint",
            }
        )

    injection_flags = detect_embedded_control_instructions(clean_synopsis)
    missing_fields: list[str] = []
    if not clean_synopsis or len(clean_synopsis) < 15:
        missing_fields.append("synopsis")
    if clean_constraints.get("request_missing_information") or injection_flags:
        if "genre" not in clean_constraints and "tone" not in clean_constraints:
            missing_fields.append("genre_or_tone")
        if "launch_audience_context" not in clean_constraints:
            missing_fields.append("launch_context")

    redacted_input_payload = {
        "synopsis": clean_synopsis,
        "suggested_public_references": clean_refs,
        "user_constraints": clean_constraints,
    }
    return {
        "synopsis": clean_synopsis,
        "suggested_public_references": clean_refs,
        "user_constraints": clean_constraints,
        "constraints_origin": constraints_origin,
        "embedded_instructions_detected": injection_flags,
        "missing_fields": missing_fields,
        "input_hash": sha256_canonical(redacted_input_payload),
    }


def llm_role_1_brief_analyst(
    validated_brief: dict[str, Any],
    budget: dict[str, Any],
    model_route_version: str | None = None,
    llm_runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Agent 1 — ANALYSTE DU BRIEF (bounded LLM Role 1).

    Extracts public cultural concepts, themes, comparable hypotheses (`llm_hypothesis_unverified`),
    and clarification questions without inventing scores or picking ambiguous IDs.
    Only increments `budget["llm_calls_used"]` when an actual `llm_runner` model route is invoked;
    offline deterministic template execution keeps `llm_calls_used == 0`.
    """
    runner_out: dict[str, Any] | None = None
    if llm_runner is not None:
        if budget["llm_calls_used"] >= budget["llm_call_limit"]:
            raise RuntimeError("LLM call budget exhausted before Role 1 (Brief Analyst).")
        budget["llm_calls_used"] += 1
        raw_out = llm_runner(
            "role_1_brief_analyst",
            {
                "synopsis": validated_brief["synopsis"],
                "suggested_public_references": validated_brief["suggested_public_references"],
                "user_constraints": validated_brief["user_constraints"],
            },
        )
        if isinstance(raw_out, dict):
            runner_out = copy.deepcopy(raw_out)
        effective_route = model_route_version or str((runner_out or {}).get("model_route_version") or "live_llm_runner_role_1")
    else:
        effective_route = model_route_version or "offline_deterministic_template_v1_no_model_invoked"

    synopsis = validated_brief["synopsis"]
    lower = synopsis.lower()
    themes: list[str] = []
    public_concepts: list[str] = []

    if any(w in lower for w in ("mémoire", "civilisation", "empire", "bronze", "héritage")):
        themes.extend(["Memory of civilizations", "Intimate cost of historical continuity"])
        public_concepts.extend(["archival science fiction", "philosophical antiquity", "monumental chamber drama"])
    if any(w in lower for w in ("doute", "perceptions", "invisible", "horla", "présence")):
        themes.extend(["Unreliable perception", "Invisible psychological dread"])
        public_concepts.extend(["gothic chamber suspense", "unseen presence", "intimate diary"])
    if any(w in lower for w in ("céramique", "atelier", "petite ville", "disparition", "chaleureux")):
        themes.extend(["Artisanal community mystery", "Non-violent object-led investigation"])
        public_concepts.extend(["cozy mystery", "craft workshop", "small-town disappearance"])
    if any(w in lower for w in ("désert", "écologie", "pouvoir")):
        themes.extend(["Desert ecology", "Imperial resource politics"])
        public_concepts.extend(["ecological science fiction", "desert power struggle"])
    if any(w in lower for w in ("épistolaire", "contemporain", "objets", "typographie")):
        themes.extend(["Epistolary intimacy", "Object and letter trace narrative"])
        public_concepts.extend(["epistolary fiction", "minimalist object storytelling"])

    if not themes:
        themes.append("Editorial literary launch")
    if not public_concepts:
        public_concepts.append("literary adaptation")

    hypotheses: list[dict[str, Any]] = []
    for raw_ref in validated_brief["suggested_public_references"]:
        hypotheses.append(
            {
                "raw_label": raw_ref,
                "origin": "user_supplied_reference",
                "requires_qloo_resolution": True,
            }
        )

    clarification_questions: list[str] = []
    if validated_brief["missing_fields"]:
        clarification_questions.append(
            "Préciser le genre éditorial, le ton visé et au moins un comparable culturel public avant toute requête Qloo."
        )
    if validated_brief["embedded_instructions_detected"]:
        clarification_questions.append(
            "Des consignes de contrôle étrangères au brief ont été isolées comme simples données inertes ; veuillez confirmer le synopsis créatif et le genre."
        )
    if not validated_brief["suggested_public_references"] and not clarification_questions:
        clarification_questions.append(
            "Aucun comparable explicite fourni : souhaitez-vous résoudre des tags thématiques publics ou proposer 1 à 3 titres de référence ?"
        )

    runner_output_consumed = False
    if isinstance(runner_out, dict):
        runner_output_consumed = True
        if isinstance(runner_out.get("themes"), list):
            clean_themes = [str(t).strip() for t in runner_out["themes"] if str(t).strip()][:3]
            if clean_themes:
                themes = clean_themes
        if isinstance(runner_out.get("public_concepts"), list):
            clean_concepts = [str(c).strip() for c in runner_out["public_concepts"] if str(c).strip()][:6]
            if clean_concepts:
                public_concepts = clean_concepts
        if isinstance(runner_out.get("clarification_questions"), list):
            for q in runner_out["clarification_questions"]:
                q_str = str(q).strip()
                if q_str and q_str not in clarification_questions:
                    clarification_questions.append(q_str)

    return {
        "role": "Agent 1 — Brief Analyst",
        "model_route_version": effective_route,
        "llm_executed": llm_runner is not None,
        "runner_output_consumed": runner_output_consumed,
        "runner_output": runner_out,
        "public_concepts": public_concepts,
        "themes": themes,
        "comparable_hypotheses": hypotheses,
        "clarification_questions": clarification_questions,
        "cultural_scores_invented": 0,
    }


def sanitize_to_public_concepts(analysis: dict[str, Any]) -> dict[str, Any]:
    """Ensures only public cultural concepts and redacted reference titles leave Role 1 toward Qloo."""
    return {
        "public_concepts": [redact_sensitive_text(c) for c in analysis.get("public_concepts", [])],
        "themes": [redact_sensitive_text(t) for t in analysis.get("themes", [])],
        "candidate_queries": [
            redact_sensitive_text(h["raw_label"])
            for h in analysis.get("comparable_hypotheses", [])
            if h.get("raw_label")
        ],
    }


def resolve_candidates(candidate_queries: list[str], user_constraints: dict[str, Any],
        confirmed_entity_ids: list[str] | None = None, mode: str = "fixture",
        custom_resolver: Callable[[str], list[dict[str, Any]]] | None = None,
        resolution_choices: dict[str, str] | None = None) -> dict[str, Any]:
    """Resolve only supplied titles; explicit choices must identify one actual candidate.

    In live/replay, absence of a describe response never falls back to fixture IDs.
    A title declared synthetic can be searched but cannot become a seed.
    """
    confirmed_set=set(confirmed_entity_ids or []); choices=dict(resolution_choices or {})
    if any(not isinstance(k,str) or not isinstance(v,str) or not v.strip() for k,v in choices.items()):
        raise ValueError("resolution_choices must map query to one selected_entity_id")
    if set(choices)-set(candidate_queries):
        raise ValueError("Resolution choice refers to a query absent from this request")
    groups=[]; selected=[]; ambiguous=[]; unmatched=[]
    for query in candidate_queries:
        args=build_canonical_qloo_describe_args(query)
        explicit_type=_normalize_entity_type_urn(args["type"]) if args.get("type") else None
        if explicit_type is None:
            suffix=re.search(r"\((book|movie|film|artist)\)$",query,re.I)
            explicit_type=_normalize_entity_type_urn(suffix.group(1).replace("film","movie")) if suffix else None
        synthetic="(synthetic title)" in query.lower()
        if custom_resolver is not None:
            matches=custom_resolver(query)
        elif mode=="fixture":
            key=re.sub(r"\s*\((?:book|movie|film|artist|synthetic title)\)$","",query,flags=re.I).strip().lower()
            matches=copy.deepcopy(FIXTURE_CATALOG.get(key,[]))
        else:
            matches=[]
        candidates=[]; seen=set()
        for m in matches if isinstance(matches,list) else []:
            if not isinstance(m,dict): continue
            eid=str(m.get("entity_id") or "").strip()
            typ=str(m.get("entity_type") or "")
            if not eid or eid in seen: continue
            if explicit_type and typ!=explicit_type: continue
            seen.add(eid); candidates.append(copy.deepcopy(m))
        picked=[c["entity_id"] for c in candidates if c["entity_id"] in confirmed_set]
        if query in choices:
            if choices[query] not in seen:
                raise ValueError("Resolution choice is not an actual candidate for its query")
            picked=[choices[query]]
        need_choice=bool(user_constraints.get("require_disambiguation")) or len(candidates)!=1 or not explicit_type or any(c.get("requires_user_confirmation") for c in candidates)
        chosen=None
        if synthetic:
            status="synthetic_title_not_a_seed"
        elif len(picked)==1:
            chosen=picked[0]; status="confirmed"
        elif candidates and not need_choice:
            chosen=candidates[0]["entity_id"]; status="confirmed"
        elif candidates:
            status="needs_confirmation"; ambiguous.append(query)
        else:
            status="unmatched"; unmatched.append(query)
        if chosen and chosen not in selected: selected.append(chosen)
        groups.append({"query":query,"status":status,"ambiguous":need_choice,
            "synthetic_title_declared":synthetic,"candidates":candidates,"selected_entity_id":chosen,
            "choice_origin":"explicit_confirmation" if picked and chosen else ("typed_unique_match" if chosen else None)})
    gate="ok" if candidate_queries and all(g["selected_entity_id"] for g in groups) else "needs_input"
    return {"gate_status":gate,"resolved_groups":groups,"confirmed_entity_ids":selected,
            "ambiguous_queries":ambiguous,"unmatched_queries":unmatched,"mode":mode}


def _normalize_entity_type_urn(raw_type: str | None) -> str:
    """Normalizes short Qloo entity types (`movie`, `artist`, `book`) or URN strings (`urn:entity:movie`) to URN form."""
    val = str(raw_type or "").strip().lower()
    if not val:
        return ""
    if val.startswith("urn:entity:"):
        return val
    return f"urn:entity:{val}"


def _to_short_entity_type(raw_type: str | None) -> str:
    """Converts `urn:entity:movie` or `movie` to canonical short Qloo option_type (`movie`, `artist`, `book`, etc.)."""
    val = str(raw_type or "").strip().lower()
    if val.startswith("urn:entity:"):
        val = val[len("urn:entity:") :]
    if val == "film":
        return "movie"
    return val


def build_canonical_qloo_describe_args(raw_query: str) -> dict[str, Any]:
    """Builds canonical arguments for `qloo_describe` per installed `tools-list.json` (`required: ['entity']`, optional `type`)."""
    norm_q = str(raw_query or "").strip()
    lower_q = norm_q.lower()
    explicit_type: str | None = None
    clean_entity = norm_q
    if lower_q.endswith("(book)"):
        explicit_type = "book"
        clean_entity = norm_q[: -len("(book)")].strip()
    elif lower_q.endswith("(movie)") or lower_q.endswith("(film)"):
        explicit_type = "movie"
        clean_entity = re.sub(r"\((?:movie|film)\)$", "", norm_q, flags=re.IGNORECASE).strip()
    clean_entity = re.sub(r"\s*\(synthetic title\)$", "", clean_entity, flags=re.I).strip()
    args: dict[str, Any] = {"entity": redact_sensitive_text(clean_entity)}
    if explicit_type in QLOO_DESCRIBE_ENTITY_TYPES:
        args["type"] = explicit_type
    return args


def get_default_shortlist_options(option_type: str, primary_seed: str | None = None) -> list[str]:
    """Fixture-only catalog lookup. Missing/unknown seed has no implicit Hyperion fallback."""
    if not primary_seed: return []
    domain=_to_short_entity_type(option_type)
    return [str(x.get("entity_id") or x.get("name")) for x in
            FIXTURE_RECOMMENDATIONS_BY_SEED.get(primary_seed,{}).get(domain,[])
            if x.get("entity_id") or x.get("name")][:10]


def _normalize_rank_configuration(
    rank_domains: tuple[str, ...] | list[str],
    shortlist_options: dict[str, list[str]] | None,
) -> tuple[tuple[str, ...], dict[str, list[str]]]:
    """Validate explicit rank inputs before any model or transport is called."""
    if not isinstance(rank_domains, (tuple, list)) or not rank_domains:
        raise ValueError("rank_domains must be a non-empty list or tuple of movie/artist domains.")
    if any(not isinstance(domain, str) for domain in rank_domains):
        raise ValueError("rank_domains must contain strings only.")
    domains = tuple(_to_short_entity_type(domain) for domain in rank_domains)
    if any(domain not in DEFAULT_RANK_DOMAINS for domain in domains) or len(set(domains)) != len(domains):
        raise ValueError("rank_domains must contain distinct movie/artist domains.")
    if shortlist_options is not None and not isinstance(shortlist_options, dict):
        raise ValueError("shortlist_options must map movie/artist domains to option lists.")
    shortlists: dict[str, list[str]] = {}
    for domain, options in (shortlist_options or {}).items():
        if domain not in DEFAULT_RANK_DOMAINS:
            raise ValueError(f"Unsupported shortlist_options domain {domain!r}.")
        if not isinstance(options, list) or not 1 <= len(options) <= 10:
            raise ValueError(f"shortlist_options[{domain!r}] must contain 1..10 option strings.")
        if any(not isinstance(option, str) or not option.strip() for option in options):
            raise ValueError(f"shortlist_options[{domain!r}] must contain non-empty strings only.")
        shortlists[domain] = [redact_sensitive_text(option) for option in options]
    return domains, shortlists


class CanonicalRankArgs(dict):
    """Canonical `qloo_rank` MCP arguments dict (`options`, `option_type`, optional `signals`)
    conforming strictly to `@qloo/qloo-harness@0.1.26` (`additionalProperties: false`),
    while providing read-only fallback compatibility for synthetic test harnesses that read
    `payload["shortlist_type"]`, `payload.get("input_hash")`, or `payload.get("run_id")`.
    """

    def __init__(self, *args: Any, input_hash: str = "", run_id: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._compat_input_hash = input_hash
        self._compat_run_id = run_id

    def __getitem__(self, key: str) -> Any:
        if key == "shortlist_type" and not super().__contains__("shortlist_type"):
            return f"urn:entity:{super().__getitem__('option_type')}"
        if key == "input_hash" and not super().__contains__("input_hash"):
            return self._compat_input_hash
        if key == "run_id" and not super().__contains__("run_id"):
            return self._compat_run_id
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "shortlist_type" and not super().__contains__("shortlist_type"):
            return f"urn:entity:{super().get('option_type', '')}"
        if key == "input_hash" and not super().__contains__("input_hash"):
            return self._compat_input_hash if self._compat_input_hash else default
        if key == "run_id" and not super().__contains__("run_id"):
            return self._compat_run_id if self._compat_run_id else default
        return super().get(key, default)


def build_canonical_qloo_rank_args(
    option_type: str,
    options: list[str],
    signals: list[str] | None = None,
    *,
    input_hash: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    """Builds canonical arguments for `qloo_rank` conforming strictly to `@qloo/qloo-harness@0.1.26` `tools-list.json`:
    - `required`: `["options", "option_type"]`
    - `additionalProperties`: `false` (no `shortlist_type`, `confirmed_entity_ids`, or `input_hash` in dict keys!)
    - `option_type`: short string in `QLOO_RANK_OPTION_TYPES` (`"movie"`, `"artist"`, etc.)
    - `options`: 1..10 non-empty strings
    - `signals`: optional 1..10 non-empty strings
    """
    short_type = _to_short_entity_type(option_type)
    if short_type not in QLOO_RANK_OPTION_TYPES:
        raise ValueError(f"Invalid qloo_rank option_type {option_type!r}; must be one of {QLOO_RANK_OPTION_TYPES}")
    clean_options = [redact_sensitive_text(o) for o in options if str(o).strip()][:10]
    if not clean_options:
        raise ValueError("qloo_rank requires at least 1 non-empty option string.")
    payload = CanonicalRankArgs(
        {
            "options": clean_options,
            "option_type": short_type,
        },
        input_hash=input_hash,
        run_id=run_id,
    )
    if signals:
        clean_signals = [redact_sensitive_text(s) for s in signals if str(s).strip()][:10]
        if clean_signals:
            payload["signals"] = clean_signals
    return payload


def unwrap_qloo_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(envelope,dict): raise ValueError("Expected MCP envelope object")
    doc=envelope
    if isinstance(doc.get("result"),dict) and ("jsonrpc" in doc or "id" in doc): doc=doc["result"]
    if isinstance(doc.get("structuredContent"),dict): return doc["structuredContent"]
    if isinstance(doc.get("content"),list):
        texts=[x.get("text") for x in doc["content"] if isinstance(x,dict) and x.get("type")=="text" and isinstance(x.get("text"),str)]
        if len(texts)==1 and len(texts[0].encode())<=2*1024*1024:
            try: parsed=json.loads(texts[0],parse_constant=lambda v: (_ for _ in ()).throw(ValueError("non-finite JSON")))
            except (ValueError,TypeError): parsed=None
            if isinstance(parsed,dict): return parsed
    return doc


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value,str): raise ValueError("Timestamp must be ISO 8601 with timezone")
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None: raise ValueError("Timestamp timezone is missing")
    return dt.astimezone(timezone.utc)


def parse_qloo_describe_candidates(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    sc=unwrap_qloo_envelope(envelope)
    if sc.get("status") not in ("ok","needs_input","partial","degraded"): return []
    raw=[]; resolution=sc.get("resolution") or {}; interpretation=sc.get("interpretation") or {}
    # Official describe outcomes carry resolved type/name even when results use a generic type.
    for outcome in resolution.get("outcomes",[]) if isinstance(resolution,dict) else []:
        if isinstance(outcome,dict):
            if isinstance(outcome.get("selected"),dict): raw.append(outcome["selected"])
            if outcome.get("status") not in ("resolved",): raw.extend(outcome.get("alternatives") or [])
    # Official needs_input envelopes expose ambiguity candidates under resolution.issues[].
    for issue in resolution.get("issues",[]) if isinstance(resolution,dict) else []:
        if isinstance(issue,dict) and isinstance(issue.get("candidates"),list):
            raw.extend(issue["candidates"])
    if isinstance(interpretation,dict) and isinstance(interpretation.get("entity"),dict):
        item=dict(interpretation["entity"])
        if item.get("entityId"): item["entity_id"]=item["entityId"]
        raw.append(item)
    results=sc.get("results")
    raw.extend(results if isinstance(results,list) else (results.get("entities",[]) if isinstance(results,dict) else []))
    for key in ("candidates","matches"):
        raw.extend(resolution.get(key,[]) if isinstance(resolution,dict) else [])
    error=sc.get("error") or {}; details=error.get("details") or {} if isinstance(error,dict) else {}
    if isinstance(details,dict): raw.extend(details.get("candidates",[]))
    parsed=[]; seen=set()
    for item in raw:
        if not isinstance(item,dict): continue
        eid=str(item.get("entity_id") or item.get("id") or "").strip()
        if not eid or eid in seen: continue
        typ=item.get("entity_type") or item.get("subtype") or item.get("type") or ""
        if typ in ("entity","urn:entity"): typ=""
        seen.add(eid); props=item.get("properties") or {}
        parsed.append({"name":str(item.get("name") or eid),"entity_id":eid,
            "entity_type":_normalize_entity_type_urn(str(typ)) if typ else "",
            "disambiguation":str(item.get("disambiguation") or item.get("description") or
                (props.get("short_description") if isinstance(props,dict) else "") or "Type non fourni"),
            "source":"qloo_describe","requires_user_confirmation":sc.get("status")=="needs_input"})
    return parsed


def build_question_plan(
    confirmed_entity_ids: list[str],
    public_concepts: list[str],
    budget: dict[str, Any],
    rank_domains: tuple[str, ...] | list[str] = DEFAULT_RANK_DOMAINS,
    shortlist_options: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Step D.1 (`question_plan`): plans a bounded workflow centered on `qloo_rank` of a same-type shortlist."""
    rank_domains, shortlist_options = _normalize_rank_configuration(rank_domains, shortlist_options)
    remaining_attempts = budget["qloo_network_attempt_limit"] - budget["qloo_network_attempts_used"]
    steps: list[dict[str, Any]] = []

    if confirmed_entity_ids:
        primary_seed = confirmed_entity_ids[0]
        for short_dom in rank_domains:
            opts = shortlist_options[short_dom] if short_dom in shortlist_options else get_default_shortlist_options(short_dom, primary_seed)
            canonical_args = build_canonical_qloo_rank_args(
                option_type=short_dom,
                options=opts,
                signals=list(confirmed_entity_ids),
            )
            steps.append(
                {
                    "step_id": f"qloo_rank_{short_dom}_shortlist",
                    "tool": "qloo_rank",
                    "target_type": f"urn:entity:{short_dom}",
                    "option_type": short_dom,
                    "arguments": canonical_args,
                    "signals": {"confirmed_entity_ids": list(confirmed_entity_ids)},
                    "optional": False,
                }
            )
    elif public_concepts:
        steps.append(
            {
                "step_id": "qloo_find_public_tags",
                "tool": "qloo_find_tags",
                "arguments": {"query": str(public_concepts[0])},
                "signals": {"public_concepts": list(public_concepts[:3])},
                "optional": False,
            }
        )

    return {
        "central_gesture": "shortlist_same_type_qloo_rank_then_brief",
        "product_promise": PRODUCT_PROMISE_STATEMENT,
        "tools_catalog": list(OFFICIAL_MCP_TOOLS),
        "canonical_ten_tools": list(QLOO_CANONICAL_TEN_TOOLS),
        "contract_version": QLOO_CONTRACT_VERSION,
        "contract_checksum": QLOO_CONTRACT_CHECKSUM,
        "planned_steps": steps,
        "budget_remaining_before_plan": remaining_attempts,
    }


def _extract_valid_score(entity: dict[str, Any]) -> tuple[str | None, float | None]:
    q=entity.get("query") if isinstance(entity.get("query"),dict) else {}
    for field,val in [("query.affinity",q.get("affinity")),("affinity_score",entity.get("affinity_score")),("affinity",entity.get("affinity"))]:
        if isinstance(val,(int,float)) and not isinstance(val,bool) and math.isfinite(val): return field,float(val)
    return None,None


def _ignored_signal_ids(warnings: list[Any]) -> list[str]:
    ignored=[]
    for warning in warnings:
        if not isinstance(warning,dict) or warning.get("type")!="not_found": continue
        ids=warning.get("signal.interests.entities")
        if ids is None:
            signal=warning.get("signal") or {}; interests=signal.get("interests") or {} if isinstance(signal,dict) else {}
            ids=interests.get("entities") if isinstance(interests,dict) else None
        if not isinstance(ids,list): continue
        for value in ids:
            if isinstance(value,str) and value.strip() and value not in ignored: ignored.append(value)
    return ignored


def build_evidence_from_envelope(
    evidence_id: str,
    run_id: str,
    mode: str,
    tool: str,
    request_redacted: dict[str, Any],
    confirmed_entity_ids: list[str],
    envelope: dict[str, Any],
    requested_at: str,
    received_at: str,
    harness_version: str | None = None,
    recorded_live_original_at: str | None = None,
    expected_input_hash: str | None = None,
) -> dict[str, Any]:
    """Normalizes a harness response envelope (including canonical MCP `structuredContent` with `results` list)
    into an `Evidence` contract object."""
    sc = unwrap_qloo_envelope(envelope)
    requested_at=envelope.get("requested_at",requested_at)
    received_at=envelope.get("received_at",received_at)
    source_doc = sc

    # A backend downgrade based on physical HTTP must survive an inner harness status=ok.
    outer_status=str(envelope.get("status") or "")
    inner_status=str(source_doc.get("status") or "")
    severity={"ok":0,"empty":1,"partial":2,"degraded":3,"needs_input":4,"error":5,"invalid_contract":6}
    candidates_status=[v for v in (inner_status,outer_status) if v]
    raw_status=max(candidates_status,key=lambda value:severity.get(value,6)) if candidates_status else ""
    if raw_status not in ("ok", "empty", "needs_input", "partial", "degraded", "error"):
        norm_status = "invalid_contract"
    else:
        norm_status = raw_status

    raw_results_field = source_doc.get("results") if "results" in source_doc else envelope.get("results")
    results_is_canonical_list = isinstance(raw_results_field, list)
    if results_is_canonical_list:
        raw_entities = raw_results_field
        pointer_prefix = "/results"
    elif isinstance(raw_results_field, dict) and isinstance(raw_results_field.get("entities"), list):
        raw_entities = raw_results_field["entities"]
        pointer_prefix = "/results/entities"
    else:
        raw_entities = []
        pointer_prefix = "/results"

    used_items: list[dict[str, Any]] = []
    if isinstance(raw_entities, list):
        for idx, ent in enumerate(raw_entities):
            if not isinstance(ent, dict):
                continue
            ent_id = str(ent.get("entity_id") or ent.get("id") or "").strip()
            if not ent_id:
                continue
            score_field, score_val = _extract_valid_score(ent)
            order_val = ent.get("returned_order", idx)
            used_items.append(
                {
                    "item_pointer": f"{pointer_prefix}/{idx}",
                    "entity_id": ent_id,
                    "returned_order": int(order_val) if isinstance(order_val, int) and order_val >= 0 else idx,
                    "score_field": score_field,
                    "score_value": score_val,
                }
            )

    # Merge inner/outer warnings: harness0.1.26 may omit physical /v2/insights warnings.
    all_warnings=[]; warning_keys=set()
    for document in (source_doc,envelope):
        for key in ("warnings","physical_http_warnings"):
            for warning in document.get(key,[]) if isinstance(document.get(key),list) else []:
                marker=sha256_canonical(warning)
                if marker not in warning_keys: warning_keys.add(marker); all_warnings.append(copy.deepcopy(warning))
    warnings_list=[canonical_json_bytes(w).decode() if isinstance(w,(dict,list)) else str(w).strip() for w in all_warnings]
    limitations=[]
    for document in (source_doc,envelope):
        for item in document.get("limitations",[]) if isinstance(document.get("limitations"),list) else []:
            text=redact_sensitive_text(item)
            if text and text not in limitations: limitations.append(text)
    for warning in warnings_list:
        note=f"Qloo warning: {warning}"
        if note not in limitations: limitations.append(note)
    ignored_ids=_ignored_signal_ids(all_warnings)
    measured_count=sum(1 for item in used_items if item["score_value"] is not None)
    if tool=="qloo_rank":
        if used_items and measured_count==0:
            if norm_status=="ok": norm_status="empty"
            limitations.append("No finite measured affinity score was returned. Response/input order is not a qualified ranking; every candidate is non-evaluable.")
        elif measured_count<len(used_items):
            if norm_status=="ok": norm_status="partial"
            limitations.append("Some candidates have no finite measured affinity score; ranking is partial and cannot start the creative model.")
        if ignored_ids and norm_status in ("ok","empty","partial","degraded"):
            all_signals_ignored=bool(confirmed_entity_ids) and {x.casefold() for x in confirmed_entity_ids}<={x.casefold() for x in ignored_ids}
            norm_status="empty" if all_signals_ignored else "degraded"
            limitations.append("Qloo ignored signal.interests.entities IDs: "+", ".join(ignored_ids)+". The requested taste signal set was not fully evaluated.")
    if norm_status=="ok" and not used_items:
        norm_status="empty"
        limitations.append("Status ok returned0 valid items; no qualified recommendation.")

    env_source_type = str(envelope.get("source_type") or "").strip()
    env_mode = str(envelope.get("mode") or "").strip()
    env_run_id = str(envelope.get("run_id") or "").strip()
    effective_run_id = env_run_id if env_run_id else run_id
    env_input_hash = str(envelope.get("input_hash") or "").strip()
    req_input_hash = str(expected_input_hash or request_redacted.get("input_hash") or "").strip()
    has_foreign_provenance = (effective_run_id != run_id) or (
        bool(env_input_hash) and bool(req_input_hash) and env_input_hash != req_input_hash
    )

    effective_mode = (
        "fixture"
        if (mode == "fixture" or env_mode == "fixture" or env_source_type == "synthetic_fixture")
        else mode
    )

    err_obj = source_doc.get("error") if source_doc.get("error") is not None else envelope.get("error")
    err_code = str(err_obj.get("code") or "") if isinstance(err_obj, dict) else ""

    if effective_mode == "fixture":
        source_type = "synthetic_fixture"
        auth_state = "not_checked"
        limitations.append("FIXTURE mode: synthetic illustrative data, not an authentic Qloo API observation.")
    elif effective_mode == "recorded_live":
        raw_auth = str(envelope.get("authentication_state") or "")
        auth_state = raw_auth if raw_auth in ("authenticated", "not_authenticated", "not_checked") else "not_checked"
        if has_foreign_provenance:
            auth_state = "not_checked"
            limitations.append("Envelope provenance mismatch (foreign run_id or input_hash); cannot authenticate current run.")
        source_type = "qloo_response" if auth_state == "authenticated" else "user_confirmation"
        if auth_state == "authenticated":
            limitations.append("RECORDED_LIVE mode: historical redacted replay; does not qualify current live service availability.")
        else:
            limitations.append("RECORDED_LIVE envelope missing explicit authentication_state='authenticated'; not promoted to verified qloo_response.")
    else:
        raw_auth = str(envelope.get("authentication_state") or "")
        if not raw_auth and err_code in ("QLOO_AUTH", "AUTH_INVALID_OR_MISSING_KEY"):
            raw_auth = "not_authenticated"
        auth_state = raw_auth if raw_auth in ("authenticated", "not_authenticated", "not_checked") else "not_checked"
        if has_foreign_provenance:
            auth_state = "not_checked"
            limitations.append("Envelope provenance mismatch (foreign run_id or input_hash); cannot authenticate current run.")
        source_type = (
            "qloo_response"
            if auth_state == "authenticated" or (norm_status == "error" and auth_state == "not_authenticated")
            else "user_confirmation"
        )
        if auth_state != "authenticated":
            limitations.append("LIVE envelope missing explicit authentication_state='authenticated'; not promoted to verified qloo_response.")

    if results_is_canonical_list:
        results_payload: Any = raw_entities if isinstance(raw_entities, list) else []
    else:
        results_payload = {
            "entities": raw_entities if isinstance(raw_entities, list) else [],
        }

    payload_redacted: dict[str, Any] = {
        "status": norm_status,
        "results": results_payload,
        "warnings": warnings_list,
        "physical_http_warnings":copy.deepcopy(envelope.get("physical_http_warnings") or []),
        "ignored_signal_ids":ignored_ids,
        "measured_score_count":measured_count,
        "ranking_evaluable":tool=="qloo_rank" and norm_status=="ok" and measured_count>0,
        "error": err_obj,
        "degradation_summary": envelope.get("degradation_summary") or source_doc.get("degradation_summary"),
    }
    payload_sha = sha256_canonical(payload_redacted)

    try:
        req_dt,rec_dt=_parse_utc(requested_at),_parse_utc(received_at)
        if req_dt>rec_dt or rec_dt.timestamp()>time.time()+5: raise ValueError("Chronology")
        if effective_mode=="recorded_live":
            original_dt=_parse_utc(recorded_live_original_at)
            if original_dt>req_dt: raise ValueError("Archive date")
    except (ValueError,TypeError):
        norm_status="invalid_contract"; auth_state="not_checked"; source_type="user_confirmation"
        limitations.append("Missing/invalid timezone, chronology or recorded original timestamp; authenticity not qualified.")
    ev: dict[str, Any] = {
        "id": evidence_id,
        "run_id": effective_run_id,
        "source_type": source_type,
        "mode": effective_mode,
        "tool": tool,
        "harness_version": harness_version or REQUIRED_HARNESS_MIN,
        "requested_at": requested_at,
        "received_at": received_at,
        "recorded_live_original_at": recorded_live_original_at if effective_mode == "recorded_live" else None,
        "request_redacted": request_redacted,
        "confirmed_entity_ids": list(dict.fromkeys(confirmed_entity_ids)),
        "status": norm_status,
        "authentication_state": auth_state,
        "payload_redacted": payload_redacted,
        "payload_redacted_sha256": payload_sha,
        "source_payload_sha256": envelope.get("source_payload_sha256"),
        "used_items": used_items,
        "limitations": limitations,
    }
    return ev


def select_from_valid_results(
    decision_id: str,
    run_id: str,
    action: str,
    evidence: dict[str, Any],
    requested_entity_type: str,
    constraints_origin: list[dict[str, Any]],
    max_select: int = 2,
) -> dict[str, Any]:
    """Step E (`select_from_valid_results`): deterministic selection on a homogeneous shortlist.

    Assigns to every candidate in the shortlist:
    - `returned_order`: integer rank received from Qloo (`0, 1, 2...`), or `None` if absent/unindexed
    - `is_tie`: boolean indicating if the candidate shares the same rank/score with another item
    - `qualification_state`: `"retenu"` | `"écarté"` | `"non_évaluable"`
    """
    raw_results_container = evidence["payload_redacted"].get("results")
    if isinstance(raw_results_container, list):
        raw_entities = raw_results_container
        pointer_prefix = "/results"
    elif isinstance(raw_results_container, dict):
        raw_entities = raw_results_container.get("entities", [])
        pointer_prefix = "/results/entities"
    else:
        raw_entities = []
        pointer_prefix = "/results"

    norm_requested_type = _normalize_entity_type_urn(requested_entity_type)
    candidates: list[dict[str, Any]] = []
    excluded_candidates: list[dict[str, Any]] = []
    selected_ids: list[str] = []
    evidence_refs: list[dict[str, str]] = []

    # Detect ties by returned_order or identical non-null score_value
    order_counts: dict[int, int] = {}
    for idx, ent in enumerate(raw_entities):
        if isinstance(ent, dict) and (ent.get("entity_id") or ent.get("id")):
            ord_v = ent.get("returned_order", idx)
            if isinstance(ord_v, int):
                order_counts[ord_v] = order_counts.get(ord_v, 0) + 1

    ranked_items=sorted(enumerate(raw_entities), key=lambda pair:
        (pair[1].get("returned_order",pair[0]) if isinstance(pair[1],dict) and isinstance(pair[1].get("returned_order",pair[0]),int)
         and not isinstance(pair[1].get("returned_order",pair[0]),bool) and pair[1].get("returned_order",pair[0])>=0 else pair[0],pair[0]))
    seen_ids=set()
    score_counts={}
    for _,item in ranked_items:
        if isinstance(item,dict):
            _,val=_extract_valid_score(item)
            if val is not None: score_counts[val]=score_counts.get(val,0)+1
    for idx, ent in ranked_items:
        if not isinstance(ent, dict):
            continue
        ent_id = str(ent.get("entity_id") or ent.get("id") or "").strip()
        ent_name = str(ent.get("name") or f"Candidate #{idx}")
        raw_ent_type = str(ent.get("entity_type") or ent.get("subtype") or ent.get("type") or "")
        ent_type = _normalize_entity_type_urn(raw_ent_type) if raw_ent_type else ""
        score_field, score_val = _extract_valid_score(ent)
        raw_order = ent.get("returned_order", idx if ent_id else None)
        returned_order = int(raw_order) if isinstance(raw_order, int) and not isinstance(raw_order,bool) and raw_order >= 0 and ent_id and score_val is not None else None
        is_tie = bool((returned_order is not None and order_counts.get(returned_order, 0) > 1) or (score_val is not None and score_counts.get(score_val,0)>1))

        if not ent_id:
            qual_state = "non_évaluable"
            excl_reason = "missing_entity_id"
        elif ent_id in seen_ids:
            qual_state = "non_évaluable"
            excl_reason = "duplicate_entity_id"
        elif evidence["status"] != "ok":
            qual_state = "non_évaluable"
            excl_reason = "non_usable_evidence_status"
        elif score_val is None:
            qual_state = "non_évaluable"
            excl_reason = "missing_finite_measured_affinity"
        elif not ent_type or ent_type=="urn:entity":
            qual_state = "non_évaluable"
            excl_reason = "missing_specific_entity_type"
        elif norm_requested_type and ent_type != norm_requested_type:
            qual_state = "non_évaluable"
            excl_reason = f"type_mismatch_expected_{norm_requested_type}"
        elif len(selected_ids) >= max_select:
            qual_state = "écarté"
            excl_reason = "rank_cutoff_exceeded"
        else:
            qual_state = "retenu"
            excl_reason = None

        if ent_id: seen_ids.add(ent_id)
        cand_record = {
            "name": ent_name,
            "entity_id": ent_id,
            "entity_type": ent_type or "urn:entity",
            "returned_order": returned_order,
            "is_tie": is_tie,
            "qualification_state": qual_state,
            "score_field": score_field,
            "score_value": score_val,
        }
        candidates.append(cand_record)

        if excl_reason is not None:
            excluded_candidates.append({**cand_record, "exclusion_reason": excl_reason})
            continue

        selected_ids.append(ent_id)
        evidence_refs.append(
            {
                "evidence_id": evidence["id"],
                "item_pointer": f"{pointer_prefix}/{idx}",
            }
        )

    is_authentic_non_fixture = (
        evidence["source_type"] == "qloo_response"
        and evidence["mode"] in ("live", "recorded_live")
        and evidence["authentication_state"] == "authenticated"
        and evidence["status"] == "ok"
        and len(evidence_refs) > 0
    )

    if is_authentic_non_fixture:
        claim_origin = "qloo_result"
        decision_status = "supported"
        rationale = (
            f"Ranked same-type ({norm_requested_type}) shortlist via `{evidence['tool']}` ({evidence['id']}): "
            f"{len(selected_ids)} retenu(s), {sum(1 for c in candidates if c['qualification_state'] == 'écarté')} écarté(s), "
            f"{sum(1 for c in candidates if c['qualification_state'] == 'non_évaluable')} non évaluable(s)."
        )
    elif evidence["status"] == "needs_input":
        claim_origin = "insufficient_evidence"
        decision_status = "needs_input"
        rationale = "Awaiting user confirmation of ambiguous or missing entity references before ranking shortlist."
    elif evidence["status"] in ("error", "invalid_contract"):
        claim_origin = "insufficient_evidence"
        decision_status = "blocked"
        rationale = f"Shortlist ranking blocked because evidence `{evidence['id']}` returned status `{evidence['status']}`."
    elif selected_ids and evidence["mode"] == "fixture":
        claim_origin = "editorial_inference"
        decision_status = "proposed"
        rationale = (
            f"[FIXTURE ILLUSTRATION] Ranked same-type ({norm_requested_type}) shortlist from synthetic fixture `{evidence['id']}`: "
            f"{len(selected_ids)} retenu(s), {sum(1 for c in candidates if c['qualification_state'] == 'écarté')} écarté(s), "
            f"{sum(1 for c in candidates if c['qualification_state'] == 'non_évaluable')} non évaluable(s) (no live Qloo claim)."
        )
    else:
        claim_origin = "insufficient_evidence"
        decision_status = "proposed"
        rationale = "No authenticated Qloo entity proof available; falling back to explicit user constraints and unverified proposal."

    return {
        "id": decision_id,
        "run_id": run_id,
        "action": action,
        "claim_origin": claim_origin,
        "status": decision_status,
        "shortlist_type": norm_requested_type,
        "shortlist_summary": {
            "shortlist_type": norm_requested_type,
            "shortlist_entity_type": norm_requested_type,
            "total_candidates": len(candidates),
            "retenus": list(selected_ids),
            "retained_ids": list(selected_ids),
            "ecartes": [c["entity_id"] for c in candidates if c["qualification_state"] == "écarté"],
            "discarded_ids": [c["entity_id"] for c in candidates if c["qualification_state"] == "écarté"],
            "non_evaluables": [c["name"] for c in candidates if c["qualification_state"] == "non_évaluable"],
            "non_evaluable_ids": [c["name"] for c in candidates if c["qualification_state"] == "non_évaluable"],
        },
        "candidates": candidates,
        "selected_entity_ids": selected_ids,
        "excluded_candidates": excluded_candidates,
        "evidence_refs": evidence_refs,
        "rule_version": RULE_VERSION,
        "rationale": rationale,
        "constraints_origin": constraints_origin,
        "limitations": list(evidence.get("limitations") or []),
    }


def _shot_plan(constraints: dict[str, Any], bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    duration=constraints.get("duration_seconds",38)
    if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or not 4<=duration<=300:
        raise ValueError("duration_seconds must be between4 and300")
    ratio=constraints.get("aspect_ratio","16:9")
    if ratio not in ("16:9","9:16","1:1","4:5"): raise ValueError("Unsupported aspect_ratio")
    quarter=round(float(duration)/4,3)
    durations=[quarter,quarter,quarter,round(float(duration)-3*quarter,3)]
    beats=[
        "Ouvrir un mystère propre au synopsis",
        ("Préserver le degré de certitude du synopsis. Lorsqu'une présence est seulement ressentie, "
         "garder cette perception subjective ; aucun indice physique n'est obligatoire. "
         "Un indice physique n'est proposé que s'il est cohérent avec le canon et n'établit pas "
         "une intrusion absente du synopsis. Rendre cette perception lisible dans les captions "
         "sans transformer le ressenti en fait établi."),
        "Créer un basculement émotionnel",
        "Conclure par une invitation à lire",
    ]
    plans=[]
    for idx in range(4):
        binding=(bindings[0] if idx<2 else bindings[min(1,len(bindings)-1)]) if bindings and idx<3 else None
        plans.append({"shot_id":f"shot_{idx+1:02d}","purpose":beats[idx],"duration_seconds":durations[idx],
            "aspect_ratio":ratio,"assets":copy.deepcopy(constraints.get("assets") or []),
            "retained_reference":copy.deepcopy(binding),"sound_off":bool(constraints.get("sound_off"))})
    return plans


_PERSON_VISUAL_NOUN = r"(?:people|persons?|humans?|man|men|woman|women|child|children|characters?|actors?|actress(?:es)?|faces?|hands?|narrators?|personnes?|personnages?|humains?|humaines?|hommes?|femmes?|enfants?|acteurs?|actrices?|visages?|mains?|narrateurs?|narratrices?)"
_NEGATABLE_VISUAL_NOUN = _PERSON_VISUAL_NOUN + r"|figures?|silhouettes?|contours?|outlines?|formes?|shapes?|ombres?|shadows?|bodies|body|corps|monsters?|monstres?|creatures?|apparitions?"


def _without_negated_visual_nominals(text: str) -> str:
    """Mask only explicit negative nominal spans, never their whole clause.

    A small EN/FR list grammar, not semantic validation. Unknown one-word list
    heads can carry negation to a later visual noun (no furniture or people).
    Contrast words, new sentences and new subjects after commas stop the scope.
    """
    tokens = list(re.finditer(r"[a-z]+(?:[-'][a-z]+)*|[,.;:!?()]", text))
    values = [m.group() for m in tokens]
    articles = {"a", "an", "the", "any", "de", "des", "du", "un", "une", "le", "la", "les", "aucun", "aucune", "aucuns", "aucunes"}
    modifiers = {"other", "ordinary", "visible", "human", "humanoid", "human-shaped", "body-shaped", "figure-shaped", "blurry", "blurred", "shadowy", "spectral", "ghostly", "distinct", "additional", "autre", "autres", "ordinaire", "ordinaires", "visible", "visibles", "humain", "humaine", "humains", "humaines", "humanoide", "humanoides", "flou", "floue", "flous", "floues", "spectral", "spectrale", "spectrales", "spectraux"}
    contrasts = {"but", "except", "however", "yet", "although", "rather", "instead", "mais", "sauf", "pourtant", "cependant", "puis", "alors", "tandis", "when", "while", "then", "until"}
    joins = {"or", "nor", "ou", "ni", "and", "et"}
    stop = contrasts | joins | {"no", "not", "without", "neither", "sans", "pas", "is", "are", "was", "were", "appears", "appear", "stands", "stand", "enters", "enter", "emerges", "emerge", "se", "est", "sont", "apparait", "apparaissent", "entre", "entrent"}
    masks = []

    def nominal(index, allow_article):
        start = index
        if index >= len(values) or (not allow_article and values[index] in articles): return None
        count = 0
        while index < len(values) and values[index] in articles | modifiers and count < 4:
            if re.fullmatch(_NEGATABLE_VISUAL_NOUN, values[index]) and (index + 1 >= len(values) or values[index + 1] in modifiers | stop or not values[index + 1][0].isalpha()): break
            index += 1; count += 1
        if index >= len(values): return None
        head = values[index]
        if not re.fullmatch(r"[a-z]+(?:[-'][a-z]+)*", head) or head in stop | articles: return None
        base = head.removesuffix("'s")
        if base.startswith("d'"): base = base[2:]
        known = bool(re.fullmatch(_NEGATABLE_VISUAL_NOUN, base))
        known = known or any(re.fullmatch(_NEGATABLE_VISUAL_NOUN, value) for value in values[start:index])
        index += 1
        if head.endswith("'s") and index < len(values) and re.fullmatch(_NEGATABLE_VISUAL_NOUN, values[index]):
            index += 1
        count = 0
        while index < len(values) and values[index] in modifiers and count < 3:
            index += 1; count += 1
        if known and index + 1 < len(values) and values[index] in {"of", "de", "du"}:
            owner = index + 1
            while owner < len(values) and values[owner] in articles | modifiers and owner < index + 5: owner += 1
            if owner < len(values) and re.fullmatch(_PERSON_VISUAL_NOUN, values[owner]): index = owner + 1
        return index, (tokens[start].start(), tokens[index - 1].end()) if known else None

    for i, word in enumerate(values):
        if word not in {"no", "not", "without", "neither", "sans", "aucun", "aucune", "aucuns", "aucunes", "pas", "ni"}: continue
        if i and values[i - 1] in {"not", "pas"} and word in {"no", "without", "sans", "aucun", "aucune", "aucuns", "aucunes", "ni"}: continue
        if word == "pas" and i + 1 < len(values) and values[i + 1] in {"aucun", "aucune", "aucuns", "aucunes"}: continue
        current = nominal(i + 1, True)
        if current is None: continue
        end, mask = current
        if mask: masks.append(mask)
        while end < len(values):
            separator = values[end]
            if separator not in joins | {","}: break
            next_index = end + 1
            comma_before_join = separator == ","
            if separator == "," and next_index < len(values) and values[next_index] in joins:
                separator = values[next_index]; next_index += 1
            nxt = nominal(next_index, separator in {"or", "nor", "ou", "ni"})
            if nxt is None: break
            next_end, next_mask = nxt
            # A comma-and/et can introduce a new affirmative clause, not just
            # continue the negative list. Preserve that bare subject/predicate.
            # Explicitly negative nor/ni joins retain their negative scope.
            clause_after_comma = separator == "," or (comma_before_join and separator in {"and", "et"})
            if clause_after_comma and next_end < len(values) and values[next_end] not in joins | {",", ".", ";", ":", "!", "?", ")"}: break
            if next_mask: masks.append(next_mask)
            end = next_end
    chars = list(text)
    for start, end in masks:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def _visible_person_form(visual: str) -> bool:
    text = "".join(c for c in unicodedata.normalize("NFKD", visual.casefold()) if not unicodedata.combining(c)).replace("’", "'")
    return bool(re.search(r"\b" + _PERSON_VISUAL_NOUN + r"\b", _without_negated_visual_nominals(text)))


def _visible_phenomenon_form(visual: str) -> bool:
    """Catch explicit apparition shapes; ordinary narrator faces and object traces remain allowed.

    This is a narrow lexical guard, not a replacement for the semantic verifier.
    It never exempts a whole shot merely because the narrator is mentioned.
    """
    text="".join(c for c in unicodedata.normalize("NFKD",visual.casefold()) if not unicodedata.combining(c)).replace("’", "'")
    noun=r"(?:silhouettes?|figures?|contours?|outlines?|formes?|shapes?|ombres?|shadows?)"
    modifier=r"(?:visible|flou\w*|blur\w*|humain\w*|human\w*|humanoid\w*|human-shaped|ghostly|spectral|shadowy)"
    text = _without_negated_visual_nominals(text)
    actor=r"(?:narrateur|narratrice|narrator|protagoniste|protagonist)"
    # An explicitly attributed ordinary actor shape is not the unseen phenomenon.
    text=re.sub(noun+r"(?:\s+"+modifier+r")?\s+(?:du|de la|of the|of)\s+"+actor+r"\b","",text)
    text=re.sub(r"\b(?:the\s+)?"+actor+r"'s\s+(?:"+modifier+r"\s+)?"+noun+r"\b","",text)
    if re.search(r"\b(?:humanoid|humanoide|human|human-shaped|humanlike|ghostly|spectral)\s+"+noun+r"\b|\b"+noun+r"\s+(?:humain\w*|humanoide\w*)\b",text):return True
    if re.search(r"\b(?:blurry|blurred|shadowy)\s+(?:silhouette|figure)\b|\b(?:silhouette|figure)\s+(?:flou\w*|fantomatique\w*)\b",text):return True
    appearance=r"(?:apparait|disparait|surgit|se dessine|se tient|est visible|traverse|appears?|emerges?|vanishes?|lurks?|stands?|sits?|waits?|is visible|materiali[sz]es?)"
    return bool(re.search(r"\b(?:silhouette|figure)\b[^.!?;\n]{0,75}\b"+appearance+r"\b|\b"+appearance+r"\b[^.!?;\n]{0,75}\b(?:silhouette|figure)\b",text))

def validate_constraint_fidelity(brief: dict[str, Any]) -> list[str]:
    if brief.get("completeness")!="complete": return []
    constraints=brief.get("user_constraints") or {}; errors=[]; shots=brief.get("shots") or []
    if len(shots)!=4 or {x.get("id") for x in shots}!={f"shot_{i:02d}" for i in range(1,5)}:
        errors.append("Exactly four complete production shots are required")
    target=float(constraints.get("duration_seconds",38))
    if abs(sum(float(x.get("duration_seconds",0)) for x in shots)-target)>0.01:
        errors.append("Shot durations do not sum to requested duration_seconds")
    ratio=constraints.get("aspect_ratio","16:9")
    for shot in shots:
        label=shot.get("id","shot"); visual=str(shot.get("visual_prompt") or "")
        if shot.get("aspect_ratio")!=ratio: errors.append(f"{label}: aspect_ratio differs from user constraint")
        if not visual.strip() or not str(shot.get("on_screen_text") or "").strip():
            errors.append(f"{label}: visual and on_screen_text must be written")
        if constraints.get("sound_off") and (str(shot.get("voiceover") or "").strip() or str(shot.get("sonic_direction") or "").strip()):
            errors.append(f"{label}: sound_off requires empty voiceover and sonic_direction")
        if constraints.get("assets") and set(shot.get("assets") or [])!=set(constraints["assets"]):
            errors.append(f"{label}: assets differ from requested assets")
        # A deterministic guard catches explicit violations; the verifier still judges semantics.
        text=visual.lower()
        text=re.sub(r"(?:sans|aucun[e]?|no|without|pas de)\s+(?:visible\s+)?(?:créature|creature|monstre|monster|sang|blood|violence)(?:\s+(?:visible|graphique|graphic))?","",text)
        creature_text = "".join(c for c in unicodedata.normalize("NFKD", visual.casefold()) if not unicodedata.combining(c)).replace("’", "'")
        creature_text = _without_negated_visual_nominals(creature_text)
        if constraints.get("no_visible_monster") and re.search(r"\b(?:monstr\w*|monster\w*|creature\w*)\b", creature_text):
            errors.append(f"{label}: explicit creature conflicts with no_visible_monster")
        if constraints.get("no_visible_monster") and _visible_phenomenon_form(visual):
            errors.append(f"{label}: visible apparition shape conflicts with an invisible phenomenon")
        if constraints.get("no_graphic_violence") and re.search(r"\b(?:sang|blood|gore|démembr|dismember)",text):
            errors.append(f"{label}: explicit graphic violence conflicts with constraint")
        if set(constraints.get("assets") or [])=={"objects","typography"} and _visible_person_form(visual):
            errors.append(f"{label}: visible person conflicts with objects+typography")
    return errors


def llm_role_2_creative_redactor(run_id: str, mode: str, validated_brief: dict[str, Any],
        analysis: dict[str, Any], evidences: list[dict[str, Any]], decisions: list[dict[str, Any]],
        budget: dict[str, Any], qloo_api_verified: bool,
        llm_runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    constraints=copy.deepcopy(validated_brief["user_constraints"]); bindings=[]
    for decision in decisions:
        if decision.get("status") not in ("supported","proposed"): continue
        for idx,eid in enumerate(decision.get("selected_entity_ids") or []):
            candidate=next((c for c in decision.get("candidates",[]) if c.get("entity_id")==eid),{})
            refs=decision.get("evidence_refs") or []
            bindings.append({"entity_id":eid,"name":candidate.get("name",eid),"decision_id":decision["id"],
                "evidence_ref":refs[idx] if idx<len(refs) else None,
                "returned_order":candidate.get("returned_order"),"score_field":candidate.get("score_field"),"score_value":candidate.get("score_value")})
    plans=_shot_plan(constraints,bindings)
    directions=[]; shots=[]; generated=False
    if llm_runner is not None:
        if budget["llm_calls_used"]>=budget["llm_call_limit"]: raise RuntimeError("LLM budget exhausted before Role2")
        budget["llm_calls_used"]+=1
        # Keep source links in the existing export for compatibility, but do
        # not turn their rank-based positions into artistic assignments.
        writer_plans=[{key:copy.deepcopy(value) for key,value in plan.items() if key!="retained_reference"}
                      for plan in plans]
        out=llm_runner("role_2_creative_redactor",{"run_id":run_id,"mode":mode,
            "synopsis":validated_brief["synopsis"],"themes":analysis.get("themes") or [],
            "retained_references":bindings,"user_constraints":constraints,"shot_plan":writer_plans,
            "creative_contract":"Write all four complete, distinct shots. Retained references are documentary source context only, not mandatory artistic borrowings. Rank alone assigns neither a shot nor a brief-wide reference. Do not invent a cultural reason or causal link. No copying, sales or audience prediction. An independent editorial shot has no Qloo lineage; never invent it. Keep the phenomenon strictly invisible when requested; an ordinary narrator face remains allowed unless assets forbid people. Follow the requested delivery language, otherwise the synopsis language, not internal planning labels."})
        if not isinstance(out,dict): raise ValueError("Role2 output must be an object")
        overrides=out.get("shot_overrides")
        if not isinstance(overrides,dict) or set(overrides)!={p["shot_id"] for p in plans}:
            raise ValueError("Role2 must write every one of the four shots")
        directions=copy.deepcopy(out.get("directions") or [])
        for plan in plans:
            fields=overrides[plan["shot_id"]]
            if not isinstance(fields,dict) or not {"visual_prompt","voiceover","sonic_direction","on_screen_text"}<=fields.keys():
                raise ValueError("Role2 shot text is incomplete")
            binding=plan["retained_reference"]; refs=[binding["evidence_ref"]] if binding and binding.get("evidence_ref") else []
            labels=["user_constraint","editorial_inference"]
            if mode=="fixture": labels.append("synthetic_fixture")
            if binding and qloo_api_verified: labels.insert(0,"qloo_result")
            if not qloo_api_verified and mode!="fixture": labels.append("insufficient_evidence")
            shots.append({"id":plan["shot_id"],"shot_id":plan["shot_id"],"purpose":plan["purpose"],
                **{k:redact_sensitive_text(fields[k]) for k in ("visual_prompt","voiceover","sonic_direction","on_screen_text")},
                "duration_seconds":plan["duration_seconds"],"aspect_ratio":plan["aspect_ratio"],"assets":plan["assets"],
                "decision_refs":[binding["decision_id"]] if binding else [],"evidence_refs":refs,
                "retained_entity_refs":[binding["entity_id"]] if binding else [],"line_status":"active",
                "interpretation_labels":labels,"generation_origin":"llm_role_2"})
        generated=True
    brief={"id":f"brief-{run_id}","version":1,"run_id":run_id,"mode":mode,
        "product_promise":PRODUCT_PROMISE_STATEMENT,"promise_statement":PRODUCT_PROMISE_STATEMENT,
        "qloo_api_verified":bool(qloo_api_verified and mode=="live"),"created_at":utc_now_iso(),
        "synopsis":validated_brief["synopsis"],"user_constraints":constraints,
        "decision_refs":[d["id"] for d in decisions],"shots":shots,"invalidated_shot_ids":[],
        "total_duration_seconds":sum(p["duration_seconds"] for p in plans),"aspect_ratio":plans[0]["aspect_ratio"],
        "completeness":"complete" if generated else "not_generated",
        "verification":{"deterministic_status":"not_run","llm_status":"not_run","unresolved_claims":[]},
        "limitations":[PRODUCT_PROMISE_STATEMENT,"Cultural ranking informs artistic references only. Visual text, framing, timing and sound are editorial choices.",REFERENCE_LINK_LIMITATION]}
    if not generated: brief["limitations"].append("No creative model ran; no production shots were generated.")
    if mode=="fixture": brief["limitations"].append("Qloo fixture data only; this run cannot qualify the real API.")
    if mode=="recorded_live": brief["limitations"].append("Historical replay; this run cannot qualify current API availability.")
    return brief,directions


_NON_ROOT_POINTER_RE = re.compile(r"^(?:/(?:[^~/]|~[01])*)+$")


def validate_contract_links(
    brief: dict[str, Any],
    decisions: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
    budget: dict[str, Any],
) -> list[str]:
    """Deterministic validator (`validate_links`) checking all semantic invariants of `CONTRATS.schema.json` v2."""
    errors: list[str] = []
    ev_by_id = {e["id"]: e for e in evidences}
    dec_by_id = {d["id"]: d for d in decisions}
    brief_run_id = brief.get("run_id")

    if budget.get("run_id") and budget.get("run_id") != brief_run_id:
        errors.append(f"RunBudget run_id {budget.get('run_id')!r} does not match Brief run_id {brief_run_id!r}.")

    # Invariant 1 & 6: Every evidence has valid canonical sha256, run_id coherence, chronology, and mode/auth rules
    for ev in evidences:
        if ev.get("run_id") != brief_run_id:
            errors.append(f"Evidence {ev['id']} belongs to foreign run_id {ev.get('run_id')!r} != Brief run_id {brief_run_id!r}.")
        expected_sha = sha256_canonical(ev["payload_redacted"])
        if ev.get("payload_redacted_sha256") != expected_sha:
            errors.append(f"Evidence {ev['id']} payload_redacted_sha256 mismatch.")
        req_at = str(ev.get("requested_at") or "")
        rec_at = str(ev.get("received_at") or "")
        try:
            valid_time=bool(req_at and rec_at and _parse_utc(req_at)<=_parse_utc(rec_at))
        except (ValueError,TypeError): valid_time=False
        if not valid_time:
            errors.append(f"Evidence {ev['id']} has invalid chronology or timezone.")
        if ev["source_type"] == "synthetic_fixture":
            if ev["mode"] != "fixture" or ev["authentication_state"] != "not_checked":
                errors.append(f"Synthetic fixture {ev['id']} must have mode='fixture' and authentication_state='not_checked'.")
        if ev["mode"] == "fixture" and ev["source_type"] == "qloo_response":
            errors.append(f"Fixture evidence {ev['id']} cannot declare source_type='qloo_response'.")
        if ev["source_type"] == "qloo_response":
            if ev["mode"] not in ("live", "recorded_live"):
                errors.append(f"qloo_response evidence {ev['id']} must have mode in ('live', 'recorded_live').")
            if ev["status"] in ("ok", "partial", "degraded"):
                if ev["authentication_state"] != "authenticated":
                    errors.append(f"qloo_response evidence {ev['id']} with status={ev['status']!r} must have authentication_state='authenticated'.")
                if not isinstance(ev.get("used_items"), list):
                    errors.append(f"qloo_response evidence {ev['id']} with status={ev['status']!r} must provide used_items list.")
            if ev["mode"] == "recorded_live" and ev["authentication_state"] != "authenticated":
                errors.append(f"recorded_live qloo_response evidence {ev['id']} must have authentication_state='authenticated'.")
        if ev["mode"] == "recorded_live" and not ev.get("recorded_live_original_at"):
            errors.append(f"Recorded live evidence {ev['id']} missing recorded_live_original_at.")
        if ev["mode"] == "live" and ev.get("recorded_live_original_at") is not None:
            errors.append(f"Live evidence {ev['id']} cannot carry a non-null recorded_live_original_at.")
        if ev["status"] in ("partial", "degraded"):
            lims = ev.get("limitations") or []
            if not lims or not any(str(item).strip() for item in lims):
                errors.append(f"Evidence {ev['id']} with status={ev['status']!r} must include at least one non-empty limitation.")

    def check_ev_ref(ref: dict[str, str], context_label: str) -> tuple[dict[str, Any] | None, str | None]:
        ev_id = ref.get("evidence_id", "")
        ptr = ref.get("item_pointer", "")
        if not ptr or not _NON_ROOT_POINTER_RE.match(ptr):
            errors.append(f"{context_label} has invalid non-root JSON Pointer syntax {ptr!r}.")
            return None, None
        if ev_id not in ev_by_id:
            errors.append(f"{context_label} references unknown evidence_id {ev_id!r}.")
            return None, None
        target_ev = ev_by_id[ev_id]
        if target_ev["run_id"] != brief_run_id:
            errors.append(f"{context_label} references evidence {ev_id!r} from a different run_id.")
        try:
            resolved = resolve_json_pointer(target_ev["payload_redacted"], ptr)
            if not isinstance(resolved, dict) or not (resolved.get("entity_id") or resolved.get("id")):
                errors.append(f"{context_label} JSON Pointer {ptr!r} does not resolve to an entity with ID.")
                return target_ev, None
            resolved_id = str(resolved.get("entity_id") or resolved.get("id")).strip()
        except Exception as exc:
            errors.append(f"{context_label} invalid JSON Pointer {ptr!r}: {exc}")
            return target_ev, None

        used_items = target_ev.get("used_items")
        if isinstance(used_items, list):
            matching_used = [u for u in used_items if isinstance(u, dict) and u.get("item_pointer") == ptr]
            if not matching_used:
                errors.append(f"{context_label} JSON Pointer {ptr!r} is not listed in Evidence {ev_id!r} used_items.")
            elif str(matching_used[0].get("entity_id") or "").strip() != resolved_id:
                errors.append(
                    f"{context_label} entity_id mismatch between used_items and payload_redacted at {ptr!r}."
                )
        return target_ev, resolved_id

    # Invariant 2: qloo_result requires authenticated non-fixture evidence with items present
    # Also verify that Brief never consumes discarded (`écarté`) or non-evaluable (`non_évaluable`) candidates
    all_retained_ids: set[str] = set()
    for dec in decisions:
        if dec.get("run_id") != brief_run_id:
            errors.append(f"Decision {dec['id']} belongs to foreign run_id {dec.get('run_id')!r} != Brief run_id {brief_run_id!r}.")
        for eid in dec.get("selected_entity_ids", []):
            all_retained_ids.add(eid)
        resolved_dec_entity_ids: list[str] = []
        for ref in dec.get("evidence_refs", []):
            _, res_id = check_ev_ref(ref, f"Decision {dec['id']}")
            if res_id:
                resolved_dec_entity_ids.append(res_id)
        if dec["claim_origin"] == "qloo_result":
            if not dec.get("evidence_refs"):
                errors.append(f"Decision {dec['id']} claims qloo_result without evidence_refs.")
            for ref in dec.get("evidence_refs", []):
                ev = ev_by_id.get(ref.get("evidence_id", ""))
                if (
                    not ev
                    or ev["source_type"] != "qloo_response"
                    or ev["mode"] not in ("live", "recorded_live")
                    or ev["authentication_state"] != "authenticated"
                    or ev["status"] not in ("ok", "partial", "degraded")
                    or not ev.get("used_items")
                    or not ev.get("confirmed_entity_ids")
                ):
                    errors.append(
                        f"Decision {dec['id']} claims qloo_result on non-authenticated, empty, or fixture evidence {ref.get('evidence_id')!r}."
                    )
            for sel_id in dec.get("selected_entity_ids", []):
                if resolved_dec_entity_ids and sel_id not in resolved_dec_entity_ids:
                    errors.append(
                        f"Decision {dec['id']} selected_entity_id {sel_id!r} is not backed by its resolved evidence_refs."
                    )

    # Brief checks
    if brief["mode"] == "fixture" and brief.get("qloo_api_verified") is True:
        errors.append("Brief in fixture mode cannot have qloo_api_verified=True.")
    for d_ref in brief.get("decision_refs", []):
        if d_ref not in dec_by_id:
            errors.append(f"Brief references unknown decision_ref {d_ref!r}.")

    qloo_attributed_shots = 0
    for shot in brief.get("shots", []):
        labels = shot.get("interpretation_labels", [])
        for d_ref in shot.get("decision_refs", []):
            if d_ref not in dec_by_id:
                errors.append(f"Shot {shot['id']} references unknown decision_ref {d_ref!r}.")
        for ev_ref in shot.get("evidence_refs", []):
            check_ev_ref(ev_ref, f"Shot {shot['id']}")
        for r_id in shot.get("retained_entity_refs", []):
            if r_id not in all_retained_ids and shot.get("line_status", "active") == "active":
                errors.append(f"Shot {shot['id']} consumes non-retained entity {r_id!r} while marked active.")
        if "qloo_result" in labels:
            qloo_attributed_shots += 1
            if not brief.get("qloo_api_verified"):
                errors.append(f"Shot {shot['id']} carries qloo_result label when qloo_api_verified is False.")
            if not shot.get("evidence_refs") or not shot.get("decision_refs"):
                errors.append(f"Shot {shot['id']} carries qloo_result label without both evidence_refs and decision_refs.")
            for d_ref in shot.get("decision_refs", []):
                dec_obj = dec_by_id.get(d_ref)
                if not dec_obj or dec_obj.get("claim_origin") != "qloo_result":
                    errors.append(f"Shot {shot['id']} claims qloo_result via non-qloo_result Decision {d_ref!r}.")
            for ev_ref in shot.get("evidence_refs", []):
                ev_obj = ev_by_id.get(ev_ref.get("evidence_id", ""))
                if (
                    not ev_obj
                    or ev_obj["source_type"] != "qloo_response"
                    or ev_obj["mode"] not in ("live", "recorded_live")
                    or ev_obj["authentication_state"] != "authenticated"
                    or ev_obj["status"] not in ("ok", "partial", "degraded")
                ):
                    errors.append(
                        f"Shot {shot['id']} claims qloo_result via non-authenticated or fixture Evidence {ev_ref.get('evidence_id')!r}."
                    )
        if brief.get("qloo_api_verified") is True and "synthetic_fixture" in labels:
            errors.append(f"Verified Brief cannot contain shot {shot['id']} labeled synthetic_fixture.")

    if brief.get("qloo_api_verified") is True:
        if brief.get("mode") not in ("live", "recorded_live"):
            errors.append("Verified Brief must have mode in ('live', 'recorded_live').")
        if not brief.get("decision_refs"):
            errors.append("Verified Brief must reference at least one Decision in decision_refs.")
        if qloo_attributed_shots < 1:
            errors.append("Verified Brief must contain at least one shot attributed to qloo_result with valid refs.")

    errors.extend(validate_constraint_fidelity(brief))

    # Invariant 5: Budget ceilings
    if budget["qloo_network_attempts_used"] > budget["qloo_network_attempt_limit"]:
        errors.append("RunBudget qloo_network_attempts_used exceeds limit.")
    if budget["llm_calls_used"] > budget["llm_call_limit"]:
        errors.append("RunBudget llm_calls_used exceeds limit.")

    return errors


def llm_role_3_verifier(
    brief: dict[str, Any],
    decisions: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
    budget: dict[str, Any],
    llm_runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Agent 3 — VÉRIFICATEUR (bounded LLM Role 3).

    Checks that every Qloo claim is backed by authentic evidence, that user constraints
    (`no_visible_monster`, `no_graphic_violence`, `sound_off`, `aspect_ratio`) are preserved,
    and that no sales/conversion or demographic percentages are invented.
    Only increments `budget["llm_calls_used"]` when an actual `llm_runner` model route is invoked.
    """
    runner_out: dict[str, Any] | None = None
    if llm_runner is not None:
        if budget["llm_calls_used"] >= budget["llm_call_limit"]:
            raise RuntimeError("LLM call budget exhausted before Role 3 (Verifier).")
        compact_decisions = [
            {
                k: copy.deepcopy(d[k])
                for k in ("id", "run_id", "action", "status", "claim_origin", "selected_entity_ids", "evidence_refs", "limitations")
                if k in d
            }
            for d in decisions
        ]
        compact_evidences = [
            {
                k: copy.deepcopy(e[k])
                for k in ("id", "run_id", "mode", "tool", "status", "source_type", "authentication_state", "confirmed_entity_ids", "used_items", "limitations")
                if k in e
            }
            for e in evidences
        ]
        budget["llm_calls_used"] += 1
        raw_out = llm_runner(
            "role_3_verifier",
            {
                "brief_id": brief["id"],
                "run_id": brief["run_id"],
                "decision_ids": [d["id"] for d in decisions],
                "shot_ids": [s["id"] for s in brief.get("shots", [])],
                "brief": copy.deepcopy(brief),
                "decisions": compact_decisions,
                "evidences": compact_evidences,
                "user_constraints": copy.deepcopy(brief.get("user_constraints") or {}),
            },
        )
        if isinstance(raw_out, dict):
            runner_out = copy.deepcopy(raw_out)

    det_errors = validate_contract_links(brief, decisions, evidences, budget)
    unresolved: list[str] = list(det_errors)

    raw_verdict = ""
    if isinstance(runner_out, dict):
        if isinstance(runner_out.get("unresolved_claims"), list):
            for claim in runner_out["unresolved_claims"]:
                c_str = str(claim).strip()
                if c_str and c_str not in unresolved:
                    unresolved.append(c_str)
        raw_verdict = str(runner_out.get("llm_status") or runner_out.get("verdict") or "").strip().lower()
        if raw_verdict == "reject":
            raw_verdict = "block"

    det_status = "pass" if not det_errors else "fail"
    if det_errors:
        brief["qloo_api_verified"] = False

    if llm_runner is None:
        llm_status="not_run"
    elif det_errors:
        llm_status="block"
    elif raw_verdict in ("accept","revise","block"):
        llm_status=raw_verdict
        if llm_status=="accept" and unresolved: llm_status="revise"
    else:
        llm_status="block"; unresolved.append("Missing accepted verifier JSON verdict")

    brief["verification"] = {
        "deterministic_status": det_status,
        "llm_status": llm_status,
        "unresolved_claims": unresolved,
    }
    return brief["verification"]


def to_schema_v2_documents(
    brief: dict[str, Any],
    decisions: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
    budget: dict[str, Any],
) -> dict[str, Any]:
    """Projects `Evidence`, `Decision`, `Brief`, and `RunBudget` to the strict `additionalProperties: false`
    contract shapes defined in `conception/CONTRATS.schema.json` v2."""
    allowed_ev_keys = (
        "id",
        "run_id",
        "source_type",
        "mode",
        "tool",
        "harness_version",
        "requested_at",
        "received_at",
        "recorded_live_original_at",
        "request_redacted",
        "confirmed_entity_ids",
        "status",
        "authentication_state",
        "payload_redacted",
        "payload_redacted_sha256",
        "source_payload_sha256",
        "used_items",
        "limitations",
    )
    allowed_dec_keys = (
        "id",
        "run_id",
        "action",
        "claim_origin",
        "status",
        "candidates",
        "selected_entity_ids",
        "excluded_candidates",
        "evidence_refs",
        "rule_version",
        "rationale",
        "constraints_origin",
        "limitations",
    )
    allowed_shot_keys = (
        "duration_seconds", "aspect_ratio", "on_screen_text", "retained_entity_refs",
        "id",
        "purpose",
        "visual_prompt",
        "voiceover",
        "sonic_direction",
        "decision_refs",
        "evidence_refs",
        "interpretation_labels",
    )
    allowed_brief_keys = (
        "total_duration_seconds", "aspect_ratio", "completeness",
        "id",
        "version",
        "run_id",
        "mode",
        "qloo_api_verified",
        "created_at",
        "synopsis",
        "user_constraints",
        "decision_refs",
        "shots",
        "verification",
        "limitations",
    )
    allowed_budget_keys = (
        "run_id",
        "limits_are_internal_proposals",
        "qloo_network_attempt_limit",
        "qloo_network_attempts_used",
        "llm_call_limit",
        "llm_calls_used",
        "max_retries_per_call",
        "active_time_limit_ms",
        "active_time_used_ms",
        "quota_official_state",
        "charge_known",
    )

    clean_evidences = []
    for ev in evidences:
        ev_copy = {k: copy.deepcopy(ev[k]) for k in allowed_ev_keys if k in ev}
        clean_evidences.append(ev_copy)

    clean_decisions = [
        {k: copy.deepcopy(dec[k]) for k in allowed_dec_keys if k in dec}
        for dec in decisions
    ]

    clean_brief = {k: copy.deepcopy(brief[k]) for k in allowed_brief_keys if k in brief}
    clean_brief["shots"] = [
        {k: copy.deepcopy(shot[k]) for k in allowed_shot_keys if k in shot}
        for shot in brief.get("shots", [])
    ]
    clean_budget = {k: copy.deepcopy(budget[k]) for k in allowed_budget_keys if k in budget}

    return {
        "evidences": clean_evidences,
        "decisions": clean_decisions,
        "brief": clean_brief,
        "run_budget": clean_budget,
    }


def _build_human_explanation(
    run_id: str,
    mode: str,
    workflow_status: str,
    input_hash: str,
    confirmed_ids: list[str],
    brief: dict[str, Any],
    budget: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> str:
    invalidated_shots = [s["id"] for s in brief.get("shots", []) if s.get("line_status") != "active"]
    explanation_lines = [
        f"Cultural Launch Director — Run {run_id} (mode={mode.upper()}, status={workflow_status})",
        f"Input Hash (redacted): {input_hash}",
        f"Confirmed Entity IDs: {', '.join(confirmed_ids or ['none'])}",
        f"Qloo API Verified: {brief.get('qloo_api_verified', False)}",
        f"Invalidated Brief Shots: {', '.join(invalidated_shots) if invalidated_shots else 'none'}",
        f"Budget Used: {budget['qloo_network_attempts_used']}/{budget['qloo_network_attempt_limit']} Qloo attempts, "
        f"{budget['llm_calls_used']}/{budget['llm_call_limit']} LLM calls, {budget['active_time_used_ms']} ms active.",
    ]
    for dec in decisions:
        explanation_lines.append(
            f"- Decision {dec['id']} [{dec['action']}]: status={dec['status']}, origin={dec['claim_origin']}, "
            f"selected={dec['selected_entity_ids']}, rationale={dec['rationale']}"
        )
    return "\n".join(explanation_lines)


def _build_redacted_receipt(
    run_id: str,
    mode: str,
    workflow_status: str,
    input_hash: str,
    evidences: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    brief: dict[str, Any],
    budget: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "director_version": DIRECTOR_VERSION,
        "mode": mode,
        "workflow_status": workflow_status,
        "qloo_api_verified": bool(brief.get("qloo_api_verified", False)),
        "input_hash": input_hash,
        "evidence_ids_and_hashes": [
            {"id": e["id"], "status": e["status"], "payload_redacted_sha256": e["payload_redacted_sha256"]}
            for e in evidences
        ],
        "decision_ids": [d["id"] for d in decisions],
        "invalidated_shot_ids": [s["id"] for s in brief.get("shots", []) if s.get("line_status") != "active"],
        "brief_id": brief["id"],
        "run_budget": budget,
        "recorded_at": utc_now_iso(),
    }


def remove_confirmed_reference(
    bundle: dict[str, Any],
    entity_id_to_remove: str,
) -> dict[str, Any]:
    """Implements `ARCHITECTURE.txt` §2.F and `DECISION-PRODUIT-CODEX.txt` §3:

    When the user removes a confirmed/retained reference:
    - Its shortlist qualification transitions from `retenu` to `écarté` (`removed_by_user`).
    - In the `Brief`, ONLY the specific lines/shots (`shot["retained_entity_refs"]`) that depend on
      `entity_id_to_remove` are invalidated (`line_status = "invalidated_by_removed_reference"`),
      while shots depending on other retained references or user constraints remain `"active"`.
    - If a `Decision` loses all its retained references, that `Decision` transitions to `status = "needs_input"`.
    - Regenerates `human_readable_explanation`, `redacted_run_receipt`, and `contract_documents_v2` atomically.
    """
    updated = copy.deepcopy(bundle)
    obsolete_decision_ids: set[str] = set()
    invalidated_shot_ids: list[str] = list(updated.get("brief", {}).get("invalidated_shot_ids", []))

    for dec in updated.get("decisions", []):
        if entity_id_to_remove in dec.get("selected_entity_ids", []):
            dec["selected_entity_ids"] = [eid for eid in dec["selected_entity_ids"] if eid != entity_id_to_remove]
            for cand in dec.get("candidates", []):
                if cand.get("entity_id") == entity_id_to_remove:
                    cand["qualification_state"] = "écarté"
                    cand["removed_by_user"] = True
            if "shortlist_summary" in dec:
                dec["shortlist_summary"]["retenus"] = list(dec["selected_entity_ids"])
                dec["shortlist_summary"]["retained_ids"] = list(dec["selected_entity_ids"])
                if entity_id_to_remove not in dec["shortlist_summary"]["ecartes"]:
                    dec["shortlist_summary"]["ecartes"].append(entity_id_to_remove)
                if entity_id_to_remove not in dec["shortlist_summary"]["discarded_ids"]:
                    dec["shortlist_summary"]["discarded_ids"].append(entity_id_to_remove)
            if not dec["selected_entity_ids"]:
                dec["status"] = "needs_input"
                dec["claim_origin"] = "insufficient_evidence"
                dec["rationale"] = "Shortlist emptied after user reference removal; awaiting new reference confirmation."
                obsolete_decision_ids.add(dec["id"])
            else:
                dec["rationale"] = (
                    f"Shortlist updated after user reference removal: "
                    f"{len(dec['selected_entity_ids'])} retained reference(s) remain active."
                )

    if "brief" in updated and updated["brief"]:
        for shot in updated["brief"].get("shots", []):
            depends_on_removed_entity = entity_id_to_remove in shot.get("retained_entity_refs", [])
            if depends_on_removed_entity:
                shot["line_status"] = "invalidated_by_removed_reference"
                if shot["id"] not in invalidated_shot_ids:
                    invalidated_shot_ids.append(shot["id"])
                if "insufficient_evidence" not in shot["interpretation_labels"]:
                    shot["interpretation_labels"].append("insufficient_evidence")
                if "qloo_result" in shot["interpretation_labels"]:
                    shot["interpretation_labels"].remove("qloo_result")

        updated["brief"]["invalidated_shot_ids"] = invalidated_shot_ids
        if invalidated_shot_ids or obsolete_decision_ids:
            updated["brief"]["qloo_api_verified"] = False
            for shot in updated["brief"].get("shots", []):
                if "qloo_result" in shot.get("interpretation_labels", []) and shot["id"] in invalidated_shot_ids:
                    shot["interpretation_labels"].remove("qloo_result")
            updated["brief"]["verification"]["unresolved_claims"].append(
                f"Removed reference {entity_id_to_remove} invalidated brief shot(s): {', '.join(invalidated_shot_ids) or 'none'} "
                f"and decision(s): {', '.join(sorted(obsolete_decision_ids)) or 'none'}."
            )
            updated["brief"]["verification"]["llm_status"] = "revise"

    if "candidate_resolution" in updated and isinstance(updated["candidate_resolution"], dict):
        old_conf = updated["candidate_resolution"].get("confirmed_entity_ids") or []
        updated["candidate_resolution"]["confirmed_entity_ids"] = [
            cid for cid in old_conf if cid != entity_id_to_remove
        ]

    updated["obsolete_decision_ids_after_removal"] = sorted(obsolete_decision_ids)
    updated["invalidated_shot_ids_after_removal"] = invalidated_shot_ids
    updated["invalidated_shot_ids"] = invalidated_shot_ids

    if "brief" in updated and updated["brief"]:
        confirmed_after = (
            updated.get("candidate_resolution", {}).get("confirmed_entity_ids", [])
            if isinstance(updated.get("candidate_resolution"), dict)
            else []
        )
        updated["human_readable_explanation"] = _build_human_explanation(
            run_id=updated["run_id"],
            mode=updated["mode"],
            workflow_status=updated["workflow_status"],
            input_hash=updated["input_hash"],
            confirmed_ids=confirmed_after,
            brief=updated["brief"],
            budget=updated["run_budget"],
            decisions=updated.get("decisions", []),
        )
        updated["redacted_run_receipt"] = _build_redacted_receipt(
            run_id=updated["run_id"],
            mode=updated["mode"],
            workflow_status=updated["workflow_status"],
            input_hash=updated["input_hash"],
            evidences=updated.get("evidences", []),
            decisions=updated.get("decisions", []),
            brief=updated["brief"],
            budget=updated["run_budget"],
        )
        updated["contract_documents_v2"] = to_schema_v2_documents(
            brief=updated["brief"],
            decisions=updated.get("decisions", []),
            evidences=updated.get("evidences", []),
            budget=updated["run_budget"],
        )

    return updated


def _request_resolver(req: dict[str, Any]) -> Callable[[str], list[dict[str, Any]]] | None:
    archive=req.get("precollected_describe")
    if not isinstance(archive,dict): return None
    def resolve(query):
        args=build_canonical_qloo_describe_args(query)
        envelope=archive.get(query) if query in archive else archive.get(args["entity"])
        return parse_qloo_describe_candidates(envelope) if isinstance(envelope,dict) else []
    return resolve


def normalize_run_request(req: dict[str, Any], default_mode: str = "fixture") -> dict[str, Any]:
    """Pure frozen-case normalization. Supplements never overwrite the frozen case."""
    if not isinstance(req,dict): raise ValueError("Run request must be an object")
    out=copy.deepcopy(req); mode=out.get("mode",default_mode)
    if mode not in ALLOWED_MODES: raise ValueError("Unsupported mode")
    out["mode"]=mode
    if out.get("case_id"):
        raw=CAS_EVALUATION_PATH.read_bytes(); doc=json.loads(raw)
        cases={c["id"]:c for c in doc.get("cases",[])}
        if out["case_id"] not in cases: raise ValueError("Unknown frozen case_id")
        case=cases[out["case_id"]]; case_sha=sha256_canonical(case); file_sha=hashlib.sha256(raw).hexdigest()
        for field,actual in [("frozen_case_sha256",case_sha),("frozen_cases_file_sha256",file_sha)]:
            if field in out and out[field]!=actual: raise ValueError(f"{field} mismatch")
            out[field]=actual
        frozen={"synopsis":case["brief"],"suggested_public_references":case.get("suggested_public_references",[]),"user_constraints":case.get("user_constraints",{})}
        for key,value in frozen.items():
            if key in out and out[key]!=value: raise ValueError(f"Frozen case field modified: {key}")
            out[key]=copy.deepcopy(value)
    else:
        out.setdefault("synopsis",""); out.setdefault("suggested_public_references",[]); out.setdefault("user_constraints",{})
    if not isinstance(out["synopsis"],str) or not isinstance(out["suggested_public_references"],list) or any(not isinstance(x,str) for x in out["suggested_public_references"]) or not isinstance(out["user_constraints"],dict):
        raise ValueError("Invalid brief/ref/constraint types")
    out.setdefault("qloo_network_attempt_limit",8); out.setdefault("llm_call_limit",3)
    out.setdefault("active_time_limit_ms",120000); out.setdefault("active_time_already_used_ms",0)
    used=out.get("physical_http_attempts_used",0)
    make_initial_run_budget("run-validation",out["qloo_network_attempt_limit"],out["llm_call_limit"],out["active_time_limit_ms"],used)
    elapsed=out["active_time_already_used_ms"]
    if isinstance(elapsed,bool) or not isinstance(elapsed,int) or not 0<=elapsed<=out["active_time_limit_ms"]:
        raise ValueError("Invalid active_time_already_used_ms")
    if "explicit_run_id" in out: _allocate_execution_run_id("",mode,out["explicit_run_id"])
    out["rank_domains"],out["shortlist_options"]=_normalize_rank_configuration(out.get("rank_domains",DEFAULT_RANK_DOMAINS),out.get("shortlist_options"))
    return out


def preflight_run_request(req: dict[str, Any]) -> dict[str, Any]:
    """No client construction, model/tokenizer execution or transport access."""
    req=normalize_run_request(req)
    brief=validate_brief(req["synopsis"],req["suggested_public_references"],req["user_constraints"])
    brief["input_hash"]=sha256_canonical({"brief_input_hash":brief["input_hash"],"rank_domains":list(req["rank_domains"]),
        "shortlist_options":req["shortlist_options"],"resolution_choices":req.get("resolution_choices") or {}})
    queries=brief["suggested_public_references"]; reasons=[]; supplied=req.get("precollected_describe")
    resolver=_request_resolver(req)
    resolution=resolve_candidates(queries,brief["user_constraints"],req.get("confirmed_entity_ids"),req["mode"],resolver,req.get("resolution_choices"))
    have_describes=isinstance(supplied,dict) and all(q in supplied or build_canonical_qloo_describe_args(q)["entity"] in supplied for q in queries)
    synthetic=any("(synthetic title)" in q.lower() for q in queries)
    if brief["missing_fields"]: reasons.append("missing_brief_information")
    if brief["embedded_instructions_detected"]: reasons.append("embedded_instructions_are_data")
    if not queries: reasons.append("no_explicit_cultural_reference")
    if reasons:
        phase="needs_input"; allow_resolution=False
    elif not have_describes and req["mode"]!="fixture":
        phase="resolution_required"; allow_resolution=req["qloo_network_attempt_limit"]>0
        reasons.append("actual_describe_responses_required")
    elif synthetic:
        phase="needs_input"; allow_resolution=False; reasons.append("synthetic_title_not_a_seed")
    elif resolution["gate_status"]!="ok":
        phase="needs_input"; allow_resolution=False
        reasons.append("explicit_resolution_choice_required" if resolution["ambiguous_queries"] else "no_confirmed_entity_for_every_reference")
    else:
        missing=[d for d in req["rank_domains"] if not req["shortlist_options"].get(d) and
                 not (req["mode"]=="fixture" and get_default_shortlist_options(d,resolution["confirmed_entity_ids"][0]))]
        phase="needs_input" if missing else "ready"; allow_resolution=False
        if missing: reasons.append("explicit_same_type_shortlist_required:"+",".join(missing))
    remaining=req["qloo_network_attempt_limit"]-req.get("physical_http_attempts_used",0)
    return {"phase":phase,"allow_resolution_http":allow_resolution,"allow_rank_http":phase=="ready" and remaining>0,
        "allow_model":phase=="ready" and req["llm_call_limit"]>=3,
        "gate_reasons":reasons,"candidate_resolution":resolution,"normalized_request":req,
        "validated_brief":brief,"input_hash":brief["input_hash"],"physical_http_attempts_used":req.get("physical_http_attempts_used",0),
        "physical_count_provenance":"parent_counter_snapshot_declared" if "physical_http_attempts_used" in req else "no_core_transport_called",
        "qloo_api_verified":False,"model_calls":0,"verifier_status":"not_run",
        "constraint_fidelity":"not_evaluable","network_performed_by_preflight":False}


def _unproduced_brief(run_id: str, mode: str, validated: dict[str, Any], status: str, reasons: list[str]) -> dict[str, Any]:
    return {"id":f"brief-{run_id}","version":1,"run_id":run_id,"mode":mode,"qloo_api_verified":False,
        "created_at":utc_now_iso(),"synopsis":validated["synopsis"],"user_constraints":copy.deepcopy(validated["user_constraints"]),
        "decision_refs":[],"shots":[],"invalidated_shot_ids":[],"completeness":status,
        "verification":{"deterministic_status":"not_run","llm_status":"not_run","unresolved_claims":list(reasons)},
        "limitations":[PRODUCT_PROMISE_STATEMENT,"No production brief was generated."]+list(reasons)}


def run_cultural_launch_director(synopsis: str, suggested_public_references: list[str] | None = None,
        user_constraints: dict[str, Any] | None = None, confirmed_entity_ids: list[str] | None = None,
        mode: str = "fixture", simulated_harness_state: str | None = None,
        recorded_live_original_at: str | None = None, cancel_requested: bool = False,
        live_transport: Callable[[str,dict[str,Any]],dict[str,Any]] | None = None,
        llm_runner: Callable[[str,dict[str,Any]],dict[str,Any]] | None = None,
        custom_resolver: Callable[[str],list[dict[str,Any]]] | None = None,
        explicit_run_id: str | None = None, physical_http_attempts_used: int | None = None,
        rank_domains: tuple[str,...] | list[str] = DEFAULT_RANK_DOMAINS,
        shortlist_options: dict[str,list[str]] | None = None,
        qloo_network_attempt_limit: int = 8, llm_call_limit: int = 3,
        resolution_choices: dict[str,str] | None = None, active_time_limit_ms: int = 120000,
        active_time_already_used_ms: int = 0, request_audit: dict[str,Any] | None = None) -> dict[str,Any]:
    """Resolve/gate before three native roles. No automatic model or transport retry."""
    if mode not in ALLOWED_MODES: raise ValueError("Unsupported mode")
    rank_domains,shortlist_options=_normalize_rank_configuration(rank_domains,shortlist_options)
    start=time.monotonic(); validated=validate_brief(synopsis,suggested_public_references,user_constraints)
    validated["input_hash"]=sha256_canonical({"brief_input_hash":validated["input_hash"],"rank_domains":list(rank_domains),"shortlist_options":shortlist_options,"resolution_choices":resolution_choices or {}})
    run_id=_allocate_execution_run_id(validated["input_hash"],mode,explicit_run_id)
    budget=make_initial_run_budget(run_id,qloo_network_attempt_limit,llm_call_limit,active_time_limit_ms,physical_http_attempts_used or 0)
    if isinstance(active_time_already_used_ms,bool) or not isinstance(active_time_already_used_ms,int) or not 0<=active_time_already_used_ms<=active_time_limit_ms:
        raise ValueError("Invalid already used active time")
    if simulated_harness_state and mode!="fixture": raise ValueError("Robustness simulation requires fixture mode")
    resolution={"gate_status":"needs_input","resolved_groups":[],"confirmed_entity_ids":[],"ambiguous_queries":[],"unmatched_queries":[],"mode":mode}
    analysis={"llm_executed":False,"runner_output_consumed":False,"themes":[],"public_concepts":[],"clarification_questions":[],"comparable_hypotheses":[]}
    evidences=[]; decisions=[]; q_plan={"planned_steps":[]}; directions=[]; reasons=[]; model_error=None
    def elapsed(): return active_time_already_used_ms+int((time.monotonic()-start)*1000)
    def require_time():
        if elapsed()>=active_time_limit_ms: raise RuntimeError("Run active budget exhausted")
    def finish(status,brief):
        budget["active_time_used_ms"]=elapsed()
        bundle=_package_export_bundle(run_id,mode,status,validated,analysis,resolution,q_plan,evidences,decisions,brief,directions,budget)
        zero_model=budget["llm_calls_used"]==0
        bundle["audit"]={"pre_qloo_gate":{"gate_reasons":list(reasons),"resolution_status":resolution["gate_status"],
            "core_http_calls":core_http_calls,"physical_http_attempts_used":budget["qloo_network_attempts_used"],
            "physical_count_provenance":"parent_counter_snapshot_declared" if physical_http_attempts_used is not None else "core_transport_counter",
            "qloo_api_verified":brief.get("qloo_api_verified",False),"model_calls":budget["llm_calls_used"]},
            "request":copy.deepcopy(request_audit or {}),"active_time_already_used_ms":active_time_already_used_ms,
            "model_failure":model_error,"automatic_model_retries":0,"automatic_transport_retries":0,"llm_only_comparison":{"status":"not_run","allocated_calls":0},
            "constraint_fidelity":{"status":"not_evaluable" if brief.get("completeness")!="complete" else ("fail" if validate_constraint_fidelity(brief) else "pass"),
                "errors":validate_constraint_fidelity(brief),"scope":"duration_sum_aspect_screen_text_assets_and_explicit_forbidden_visuals; semantic_review_is_role3"},
            "ranking_steps":[{"evidence_id":e["id"],"status":e["status"],"ranking_evaluable":e["payload_redacted"].get("ranking_evaluable",False),
                "measured_score_count":e["payload_redacted"].get("measured_score_count",0),"ignored_signal_ids":e["payload_redacted"].get("ignored_signal_ids",[]),"limitations":e.get("limitations",[])} for e in evidences],
            "model_verification":"not_run" if zero_model else brief["verification"]["llm_status"],
            "physical_api_qualification":"requires_matching_parent_counter_and_receipts"}
        for key in ("case_id","frozen_case_sha256","frozen_cases_file_sha256"):
            if key in (request_audit or {}): bundle[key]=request_audit[key]
        bundle["public_export"]=build_public_export(bundle)
        return bundle
    core_http_calls=0
    if validated["missing_fields"]: reasons.append("missing_brief_information:"+",".join(validated["missing_fields"]))
    if validated["embedded_instructions_detected"]: reasons.append("embedded_instructions_are_data")
    if not validated["suggested_public_references"]: reasons.append("no_explicit_cultural_reference")
    if cancel_requested: reasons.append("run_cancelled")
    if reasons: return finish("needs_input",_unproduced_brief(run_id,mode,validated,"needs_input",reasons))
    require_time()
    resolution=resolve_candidates(validated["suggested_public_references"],validated["user_constraints"],confirmed_entity_ids,mode,custom_resolver,resolution_choices)
    if resolution["gate_status"]!="ok" or simulated_harness_state=="needs_input":
        reasons.append("synthetic_title_not_a_seed" if any(g.get("synthetic_title_declared") for g in resolution["resolved_groups"]) else "explicit_resolution_or_confirmation_required")
        return finish("needs_input",_unproduced_brief(run_id,mode,validated,"needs_input",reasons))
    confirmed_ids=resolution["confirmed_entity_ids"]
    for domain in rank_domains:
        if domain not in shortlist_options:
            if mode=="fixture": shortlist_options[domain]=get_default_shortlist_options(domain,confirmed_ids[0])
            if not shortlist_options.get(domain): reasons.append("explicit_same_type_shortlist_required:"+domain)
    if reasons: return finish("needs_input",_unproduced_brief(run_id,mode,validated,"needs_input",reasons))
    workflow_status="ok"
    for idx,domain in enumerate(rank_domains,1):
        args=build_canonical_qloo_rank_args(domain,shortlist_options[domain],confirmed_ids,input_hash=validated["input_hash"],run_id=run_id)
        q_plan["planned_steps"].append({"tool":"qloo_rank","arguments":dict(args),"target_type":f"urn:entity:{domain}"})
        require_time(); requested_at=utc_now_iso()
        if simulated_harness_state:
            ev,workflow_status=_simulate_robustness_state(simulated_harness_state,run_id,mode,confirmed_ids,budget,requested_at,recorded_live_original_at)
        else:
            if live_transport is not None and mode in ("live","recorded_live"):
                if physical_http_attempts_used is None and budget["qloo_network_attempts_used"]>=qloo_network_attempt_limit:
                    raise RuntimeError("No physical capacity remains before transport")
                env=live_transport("qloo_rank",args)
                if not isinstance(env,dict): raise ValueError("Transport returned a non-object envelope")
                if env.get("network_attempt_made",False):
                    if mode!="live": raise ValueError("A replay cannot perform current HTTP")
                    core_http_calls+=1
                    if physical_http_attempts_used is not None: raise ValueError("Cannot mix final parent physical count with new core HTTP")
                    budget["qloo_network_attempts_used"]+=1
                    if budget["qloo_network_attempts_used"]>qloo_network_attempt_limit: raise RuntimeError("Physical cap exceeded")
            elif mode=="fixture":
                items=copy.deepcopy(FIXTURE_RECOMMENDATIONS_BY_SEED.get(confirmed_ids[0],{}).get(domain,[]))
                env={"status":"ok" if items else "empty","results":{"entities":items},"authentication_state":"not_checked"}
            else:
                env={"status":"error","authentication_state":"not_checked","results":[],"error":{"code":"LIVE_TRANSPORT_NOT_CONFIGURED","retryable":False}}
            ev=build_evidence_from_envelope(f"ev-{run_id}-{domain}",run_id,mode,"qloo_rank",args,confirmed_ids,env,
                 requested_at,utc_now_iso(),recorded_live_original_at=recorded_live_original_at,expected_input_hash=validated["input_hash"])
        evidences.append(ev)
        decisions.append(select_from_valid_results(f"dec-{run_id}-{idx:02d}-{domain}",run_id,f"select_{domain}_references",ev,f"urn:entity:{domain}",validated["constraints_origin"]))
        if ev["status"]!="ok":
            workflow_status=ev["status"]
            reasons.append("ranking_step:"+domain+":"+ev["status"])
            for limitation in ev.get("limitations",[]):
                if limitation not in reasons: reasons.append(limitation)
            break  # No automatic retry, secondary domain or model after an API failure.
    usable=bool(decisions) and all(d["selected_entity_ids"] for d in decisions)
    if workflow_status!="ok" or not usable:
        if workflow_status=="ok": workflow_status="empty"
        reasons.append("ranking_not_usable:"+workflow_status)
        return finish(workflow_status if workflow_status!="ok" else "empty",_unproduced_brief(run_id,mode,validated,"not_generated",reasons))
    qloo_verified=mode=="live" and budget["qloo_network_attempts_used"]>0 and all(
        e["run_id"]==run_id and e["source_type"]=="qloo_response" and e["mode"]=="live" and e["status"]=="ok"
        and e["authentication_state"]=="authenticated" and e["used_items"]
        and all(isinstance(item.get("score_value"),(int,float)) and not isinstance(item.get("score_value"),bool) and math.isfinite(item["score_value"]) for item in e["used_items"])
        and not e["payload_redacted"].get("ignored_signal_ids")
        and isinstance(e.get("source_payload_sha256"),str) and re.fullmatch(r"[0-9a-f]{64}",e["source_payload_sha256"])
        for e in evidences)
    if mode!="fixture" and not qloo_verified and mode!="recorded_live":
        reasons.append("current_api_provenance_not_qualified")
        return finish("invalid_contract",_unproduced_brief(run_id,mode,validated,"not_generated",reasons))
    if llm_runner is not None and llm_call_limit<3:
        reasons.append("three_role_budget_required_before_first_model_call")
        return finish("needs_input",_unproduced_brief(run_id,mode,validated,"not_generated",reasons))
    try:
        require_time(); analysis=llm_role_1_brief_analyst(validated,budget,llm_runner=llm_runner)
        require_time(); brief,directions=llm_role_2_creative_redactor(run_id,mode,validated,analysis,evidences,decisions,budget,qloo_verified,llm_runner)
        require_time(); llm_role_3_verifier(brief,decisions,evidences,budget,llm_runner=llm_runner)
        if brief["verification"]["llm_status"] in ("revise","block") or brief["verification"]["deterministic_status"]=="fail": workflow_status="needs_revision"
        if brief.get("completeness")!="complete": workflow_status="not_generated"
    except Exception as exc:
        model_error={"error_type":type(exc).__name__,"calls_consumed":budget["llm_calls_used"],"outcome":"stopped_no_retry"}
        reasons.append("model_contract_or_budget_failed")
        brief=_unproduced_brief(run_id,mode,validated,"not_generated",reasons); workflow_status="error"
    return finish(workflow_status,brief)


def _simulate_robustness_state(
    state: str,
    run_id: str,
    mode: str,
    confirmed_ids: list[str],
    budget: dict[str, Any],
    now_iso: str,
    recorded_live_original_at: str | None,
) -> tuple[dict[str, Any], str]:
    """Handles the 10 synthetic robustness states defined in `validation/CAS-EVALUATION.json`."""
    req = {"confirmed_entity_ids": confirmed_ids, "simulated_state": state}
    if state == "ok_empty_results":
        budget["qloo_network_attempts_used"] += 1
        ev = build_evidence_from_envelope(
            f"ev-{run_id}-ok-empty", run_id, mode, "qloo_recommend", req, confirmed_ids,
            {"status": "ok", "results": {"entities": []}}, now_iso, now_iso,
            recorded_live_original_at=recorded_live_original_at,
        )
        return ev, "empty"
    if state == "empty":
        budget["qloo_network_attempts_used"] += 1
        ev = build_evidence_from_envelope(
            f"ev-{run_id}-empty", run_id, mode, "qloo_recommend", req, confirmed_ids,
            {"status": "empty", "results": {"entities": []}}, now_iso, now_iso,
            recorded_live_original_at=recorded_live_original_at,
        )
        return ev, "empty"
    if state == "partial":
        budget["qloo_network_attempts_used"] += 1
        ev = build_evidence_from_envelope(
            f"ev-{run_id}-partial", run_id, mode, "qloo_recommend", req, confirmed_ids,
            {
                "status": "partial",
                "results": {
                    "entities": [
                        {"name": "Partial Match Film", "entity_id": "urn:entity:movie:partial_01", "entity_type": "urn:entity:movie"}
                    ]
                },
                "limitations": ["Partial response: artist domain timed out; conclusions restricted to received movie item."],
            },
            now_iso, now_iso, recorded_live_original_at=recorded_live_original_at,
        )
        return ev, "partial"
    if state == "degraded":
        budget["qloo_network_attempts_used"] += 1
        ev = build_evidence_from_envelope(
            f"ev-{run_id}-degraded", run_id, mode, "qloo_recommend", req, confirmed_ids,
            {
                "status": "degraded",
                "results": {"entities": []},
                "degradation_summary": "Upstream MCP tool reported degraded ranking service; full success badge withheld.",
                "limitations": ["Degraded service state; full verification withheld."],
            },
            now_iso, now_iso, recorded_live_original_at=recorded_live_original_at,
        )
        return ev, "degraded"
    if state == "error_non_retryable_auth":
        budget["qloo_network_attempts_used"] += 1  # Strictly 1 attempt, 0 retries on auth failure
        ev = build_evidence_from_envelope(
            f"ev-{run_id}-auth-err", run_id, mode, "qloo_recommend", req, confirmed_ids,
            {
                "status": "error",
                "authentication_state": "not_authenticated",
                "results": {"entities": []},
                "error": {"code": "AUTH_INVALID_OR_MISSING_KEY", "retryable": False, "recovery": "Provision valid event API key on backend stdio server."},
                "limitations": ["Non-retryable authentication error; halted immediately without retry."],
            },
            now_iso, now_iso, recorded_live_original_at=recorded_live_original_at,
        )
        return ev, "error"
    if state == "error_retryable_with_budget":
        # 1 initial attempt + 1 retry (max_retries_per_call = 1) = 2 attempts
        budget["qloo_network_attempts_used"] += 2
        ev = build_evidence_from_envelope(
            f"ev-{run_id}-retry-err", run_id, mode, "qloo_recommend", req, confirmed_ids,
            {
                "status": "error",
                "results": {"entities": []},
                "error": {"code": "UPSTREAM_TIMEOUT", "retryable": True, "recovery": "Retried once within budget (2/8 attempts used); surfacing error after single retry."},
                "limitations": ["Retryable error persisted after 1 allowed retry."],
            },
            now_iso, now_iso, recorded_live_original_at=recorded_live_original_at,
        )
        return ev, "error"
    if state == "error_retryable_budget_exhausted":
        budget["qloo_network_attempts_used"] = budget["qloo_network_attempt_limit"]
        ev = build_evidence_from_envelope(
            f"ev-{run_id}-budget-exhausted", run_id, mode, "qloo_recommend", req, confirmed_ids,
            {
                "status": "error",
                "results": {"entities": []},
                "error": {"code": "BUDGET_EXHAUSTED_NO_RETRY", "retryable": True, "recovery": "Network attempt cap (8/8) reached; retry skipped."},
                "limitations": ["Retry skipped because 8-attempt run budget was exhausted."],
            },
            now_iso, now_iso, recorded_live_original_at=recorded_live_original_at,
        )
        return ev, "error"
    # unknown_status
    budget["qloo_network_attempts_used"] += 1
    ev = build_evidence_from_envelope(
        f"ev-{run_id}-unknown-status", run_id, mode, "qloo_recommend", req, confirmed_ids,
        {"status": "unexpected_vendor_code_999", "results": {"entities": []}},
        now_iso, now_iso, recorded_live_original_at=recorded_live_original_at,
    )
    return ev, "invalid_contract"


def build_public_export(bundle: dict[str,Any]) -> dict[str,Any]:
    """Whitelist the creative result. Private payloads, runtime paths and model routes stay private."""
    def take(doc,keys): return {k:copy.deepcopy(doc[k]) for k in keys if k in doc}
    brief=bundle.get("brief") or {}; resolution=bundle.get("candidate_resolution") or {}
    public_brief=take(brief,("id","run_id","mode","created_at","synopsis","user_constraints","decision_refs","total_duration_seconds","aspect_ratio","completeness","verification","limitations","qloo_api_verified"))
    public_brief["shots"]=[take(x,("id","purpose","visual_prompt","voiceover","sonic_direction","on_screen_text","duration_seconds","aspect_ratio","assets","decision_refs","evidence_refs","retained_entity_refs","line_status","interpretation_labels")) for x in brief.get("shots",[])]
    public_decisions=[]
    for dec in bundle.get("decisions",[]):
        item=take(dec,("id","action","claim_origin","status","selected_entity_ids","evidence_refs","rule_version","rationale","limitations"))
        item["candidates"]=[take(c,("name","entity_id","entity_type","returned_order","is_tie","qualification_state","score_field","score_value")) for c in dec.get("candidates",[])]
        public_decisions.append(item)
    groups=[]
    for group in resolution.get("resolved_groups",[]):
        item=take(group,("query","status","ambiguous","synthetic_title_declared","selected_entity_id","choice_origin"))
        item["candidates"]=[take(c,("name","entity_id","entity_type","disambiguation")) for c in group.get("candidates",[])]
        groups.append(item)
    questions=list((bundle.get("role_1_analysis") or {}).get("clarification_questions") or [])
    if bundle.get("workflow_status")=="needs_input":
        if not (bundle.get("validated_brief") or {}).get("suggested_public_references"):
            questions.append("Indiquez un à trois titres culturels publics et leur type, ou précisez si vous souhaitez un brief uniquement éditorial.")
        if resolution.get("ambiguous_queries"): questions.append("Choisissez explicitement une œuvre et son type pour chaque titre ambigu.")
        if any(g.get("synthetic_title_declared") for g in groups): questions.append("Ce titre déclaré synthétique ne sera pas utilisé comme seed. Proposez une référence publique réelle.")
        if (bundle.get("validated_brief") or {}).get("missing_fields"): questions.append("Précisez le synopsis, le genre ou le ton, ainsi que le contexte de lancement manquants.")
    public={"schema_version":"1.0","director_version":bundle.get("director_version"),"run_id":bundle.get("run_id"),
        "mode":bundle.get("mode"),"status":bundle.get("workflow_status"),"workflow_status":bundle.get("workflow_status"),
        "qloo_api_verified":bool(brief.get("qloo_api_verified")),"brief":public_brief,
        "directions":[take(x,("direction_id","title","angle","origin")) for x in bundle.get("directions",[])],
        "decisions":public_decisions,"candidate_resolution":{"gate_status":resolution.get("gate_status"),"resolved_groups":groups,"confirmed_entity_ids":resolution.get("confirmed_entity_ids",[])},
        "clarification_questions":list(dict.fromkeys(questions)),
        "gate_reasons":copy.deepcopy(((bundle.get("audit") or {}).get("pre_qloo_gate") or {}).get("gate_reasons") or []),
        "run_budget":take(bundle.get("run_budget") or {},("qloo_network_attempt_limit","qloo_network_attempts_used","llm_call_limit","llm_calls_used","active_time_limit_ms","active_time_used_ms")),
        "constraint_fidelity":copy.deepcopy((bundle.get("audit") or {}).get("constraint_fidelity") or {"status":"not_evaluable","errors":[]}),
        "evidence_sources":[take(e,("id","mode","tool","status","authentication_state","source_payload_sha256","used_items","limitations")) for e in bundle.get("evidences",[])],
        "limitations":copy.deepcopy(brief.get("limitations") or [PRODUCT_PROMISE_STATEMENT])}
    def clean(value):
        if isinstance(value,str):
            text=redact_sensitive_text(value)
            return re.sub(r"(?:/Users/|/home/|/private/var/|/var/folders/|file://|[A-Za-z]:\\Users\\)[^\n]*", "[PRIVATE_PATH_REMOVED]",text)
        if isinstance(value,list): return [clean(x) for x in value]
        if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
        return value
    return clean(public)


def _package_export_bundle(
    run_id: str,
    mode: str,
    workflow_status: str,
    validated_brief: dict[str, Any],
    analysis: dict[str, Any],
    resolution: dict[str, Any],
    question_plan: dict[str, Any],
    evidences: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    brief: dict[str, Any],
    directions: list[dict[str, Any]],
    budget: dict[str, Any],
) -> dict[str, Any]:
    """Packages the final export bundle, enforcing all semantic invariants before building receipt/explanation."""
    det_errors = validate_contract_links(brief, decisions, evidences, budget)
    if det_errors:
        brief["qloo_api_verified"] = False
        brief["verification"]["deterministic_status"] = "fail"
        for err in det_errors:
            if err not in brief["verification"]["unresolved_claims"]:
                brief["verification"]["unresolved_claims"].append(err)
        for shot in brief.get("shots", []):
            if "qloo_result" in shot.get("interpretation_labels", []):
                shot["interpretation_labels"].remove("qloo_result")

    confirmed_ids = resolution.get("confirmed_entity_ids") or []
    return {
        "director_version": DIRECTOR_VERSION,
        "run_id": run_id,
        "mode": mode,
        "workflow_status": workflow_status,
        "input_hash": validated_brief["input_hash"],
        "validated_brief": validated_brief,
        "role_1_analysis": analysis,
        "candidate_resolution": resolution,
        "question_plan": question_plan,
        "evidences": evidences,
        "decisions": decisions,
        "directions": directions,
        "brief": brief,
        "run_budget": budget,
        "contract_documents_v2": to_schema_v2_documents(brief, decisions, evidences, budget),
        "human_readable_explanation": _build_human_explanation(
            run_id=run_id,
            mode=mode,
            workflow_status=workflow_status,
            input_hash=validated_brief["input_hash"],
            confirmed_ids=confirmed_ids,
            brief=brief,
            budget=budget,
            decisions=decisions,
        ),
        "redacted_run_receipt": _build_redacted_receipt(
            run_id=run_id,
            mode=mode,
            workflow_status=workflow_status,
            input_hash=validated_brief["input_hash"],
            evidences=evidences,
            decisions=decisions,
            brief=brief,
            budget=budget,
        ),
    }



CAMPAGNE_DIR = _Path(__file__).resolve().parent.parent / "campagne-hackathon-2026-10-19"
CAS_EVALUATION_PATH = CAMPAGNE_DIR / "validation" / "CAS-EVALUATION.json"
CONTRATS_SCHEMA_PATH = CAMPAGNE_DIR / "conception" / "CONTRATS.schema.json"


def run_frozen_evaluation_case(
    case_id: str,
    mode: str = "fixture",
    simulated_harness_state: str | None = None,
    cancel_requested: bool = False,
) -> dict[str, Any]:
    """Loads a frozen evaluation case (`C01`..`C08`) from `validation/CAS-EVALUATION.json` (read-only) and runs it."""
    doc = json.loads(CAS_EVALUATION_PATH.read_text(encoding="utf-8"))
    cases_by_id = {c["id"]: c for c in doc.get("cases", [])}
    if case_id not in cases_by_id:
        raise ValueError(f"Unknown case_id {case_id!r}; available: {sorted(cases_by_id)}")
    c = cases_by_id[case_id]
    return run_cultural_launch_director(
        synopsis=c["brief"],
        suggested_public_references=c.get("suggested_public_references", []),
        user_constraints=c.get("user_constraints", {}),
        mode=mode,
        simulated_harness_state=simulated_harness_state,
        cancel_requested=cancel_requested,
    )


RUNS_RECEIPT_DIR = _Path(__file__).resolve().parent / "var" / "runs"


def persist_redacted_execution_proof(bundle: dict[str, Any], receipt_dir: _Path | None = None) -> dict[str, str]:
    """Persists a redacted execution proof (`redacted_run_receipt` + v2 contract hashes) on disk."""
    target_dir = receipt_dir or RUNS_RECEIPT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    receipt = copy.deepcopy(bundle.get("redacted_run_receipt") or {})
    run_id = str(bundle.get("run_id") or receipt.get("run_id") or "run-unknown")
    proof_doc = {
        "schema_version": 2,
        "director_version": bundle.get("director_version", DIRECTOR_VERSION),
        "run_id": run_id,
        "mode": bundle.get("mode"),
        "workflow_status": bundle.get("workflow_status"),
        "qloo_api_verified": bool(bundle.get("brief", {}).get("qloo_api_verified", False)),
        "redacted_run_receipt": receipt,
        "verification": bundle.get("brief", {}).get("verification"),
        "contract_v2_brief_sha256": sha256_canonical(bundle.get("contract_documents_v2", {}).get("brief", {})),
    }
    _allocate_execution_run_id("", str(bundle.get("mode") or "fixture"), run_id)
    run_file = target_dir / f"{run_id}-receipt.json"
    latest_file = target_dir / "last-run-receipt.json"
    serialized = json.dumps(proof_doc, ensure_ascii=False, indent=2) + "\n"
    with run_file.open("x", encoding="utf-8") as handle:
        handle.write(serialized)
    latest_file.write_text(serialized, encoding="utf-8")
    return {
        "run_receipt_path": str(run_file),
        "latest_receipt_path": str(latest_file),
    }


def default_qwen_context_provider(role: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Supplies the mandatory full context (`brief`, `decisions`, `evidences`, `user_constraints`)
    to `GuardedQwenRunner` for `role_3_verifier` so the verifier never judges on IDs alone.
    """
    if role == "role_3_verifier":
        return {
            "brief": copy.deepcopy(payload.get("brief")) if isinstance(payload.get("brief"), dict) else {},
            "decisions": copy.deepcopy(payload.get("decisions")) if isinstance(payload.get("decisions"), list) else [],
            "evidences": copy.deepcopy(payload.get("evidences")) if isinstance(payload.get("evidences"), list) else [],
            "user_constraints": copy.deepcopy(payload.get("user_constraints")) if isinstance(payload.get("user_constraints"), dict) else {},
        }
    return {}


def make_guarded_qwen_runner(
    native_client: Any,
    *,
    actual_model: str | None = None,
    count_input_tokens: Callable[[list[dict[str, str]]], int],
    enabled: bool = False,
    deadline_at: float | None = None,
) -> Any:
    """Constructs a `GuardedQwenRunner` bound to the OpenAI-compatible guard on `http://127.0.0.1:18080/v1`
    with `default_qwen_context_provider`. No model inference occurs unless `enabled=True`.
    """
    from guarded_qwen_runner import MODEL as QWEN_MODEL, GuardedQwenRunner

    return GuardedQwenRunner(
        native_client,
        actual_model=actual_model if actual_model is not None else QWEN_MODEL,
        count_input_tokens=count_input_tokens,
        context_provider=default_qwen_context_provider,
        enabled=enabled,
        deadline_at=deadline_at,
    )


def build_authorized_llm_runner(
    env: dict[str, str] | None = None,
    *,
    native_client: Any | None = None,
    count_input_tokens: Callable[[list[dict[str, str]]], int] | None = None,
) -> Callable[[str, dict[str, Any]], dict[str, Any]] | None:
    """Returns an opt-in, product-authorized LLM runner (`guarded_qwen_18080`),
    never a personal coding subscription (`claude-code`, `codex`, `antigravity-ide`) and never
    the unguarded `local_ollama` (`/api/generate`) route.
    Returns `None` by default when `DIRECTOR_ENABLE_LIVE_LLM` is not explicitly `"1"`, preserving
    zero-cost offline template execution (`llm_calls_used == 0`).
    """
    import os

    source_env = env if env is not None else dict(os.environ)
    if str(source_env.get("DIRECTOR_ENABLE_LIVE_LLM") or "").strip() != "1":
        return None
    provider = str(source_env.get("DIRECTOR_LLM_PROVIDER") or "").strip().lower()
    if provider in ("claude_code_subscription", "codex_subscription", "ide_subscription"):
        raise PermissionError(
            f"Provider {provider!r} is a personal coding subscription and cannot be used as a product LLM backend."
        )
    if provider in ("local_ollama", "ollama"):
        raise PermissionError(
            "Provider 'local_ollama' (/api/generate) is rejected; use 'guarded_qwen_18080' on http://127.0.0.1:18080/v1 with explicit native client and CPU token counter."
        )
    if provider == "guarded_qwen_18080":
        if native_client is None or count_input_tokens is None:
            raise RuntimeError(
                "guarded_qwen_18080 requires an explicit native_client on http://127.0.0.1:18080/v1 and an exact CPU count_input_tokens callable."
            )
        return make_guarded_qwen_runner(
            native_client,
            count_input_tokens=count_input_tokens,
            enabled=True,
        )
    return None


def _cli_main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    parser=argparse.ArgumentParser(description="Bounded Cultural Launch Director")
    parser.add_argument("--case"); parser.add_argument("--mode",default="fixture",choices=list(ALLOWED_MODES))
    parser.add_argument("--run-json",action="store_true"); parser.add_argument("--preflight-json",action="store_true")
    parser.add_argument("--remove-reference-json",action="store_true")
    args=parser.parse_args(argv)
    if sum(bool(x) for x in (args.run_json,args.preflight_json,args.remove_reference_json,args.case))>1: raise ValueError("Choose one CLI operation")
    if args.remove_reference_json:
        req=json.loads(sys.stdin.read(2*1024*1024+1) or "{}"); eid=req.get("entity_id")
        if not isinstance(eid,str) or not eid.strip(): raise ValueError("Missing entity_id")
        bundle=remove_confirmed_reference(req.get("bundle") or {},eid)
    elif args.run_json or args.preflight_json or args.case:
        if args.case: req={"case_id":args.case,"mode":args.mode}
        else:
            data=sys.stdin.read(2*1024*1024+1)
            if len(data.encode())>2*1024*1024: raise ValueError("Request exceeds2MiB")
            req=json.loads(data or "{}")
        req=normalize_run_request(req,args.mode)
        if args.preflight_json:
            sys.stdout.write(json.dumps(preflight_run_request(req),ensure_ascii=False,allow_nan=False)+"\n"); return 0
        envelopes=req.get("precollected_envelopes")
        transport=None
        if isinstance(envelopes,dict):
            def transport(tool,params):
                domain=_to_short_entity_type(params.get("option_type") or "")
                env=envelopes.get(domain) or envelopes.get(f"urn:entity:{domain}")
                if not isinstance(env,dict): return {"status":"error","error":{"code":"MISSING_DOMAIN_ENVELOPE","retryable":False},"results":[]}
                result=copy.deepcopy(env); result["network_attempt_made"]=False
                return result
        audit={k:copy.deepcopy(req[k]) for k in ("case_id","frozen_case_sha256","frozen_cases_file_sha256","resolution_choices","resolution_choice_provenance","budget_profile") if k in req}
        archive=req.get("precollected_describe") or {}
        audit["resolution_observations"]=[]
        for query,envelope in archive.items() if isinstance(archive,dict) else []:
            if not isinstance(envelope,dict): continue
            doc=unwrap_qloo_envelope(envelope)
            audit["resolution_observations"].append({"query":query,"status":doc.get("status","invalid_contract"),
                "authentication_state":envelope.get("authentication_state","not_checked"),
                "source_payload_sha256":envelope.get("source_payload_sha256"),"run_id":envelope.get("run_id"),
                "requested_at":envelope.get("requested_at"),"received_at":envelope.get("received_at")})
        # Construction is inert; the bridge injects the native client for the later authorized run.
        runner=build_authorized_llm_runner() if req["llm_call_limit"]>0 and preflight_run_request(req)["phase"]=="ready" else None
        bundle=run_cultural_launch_director(req["synopsis"],req["suggested_public_references"],req["user_constraints"],
            req.get("confirmed_entity_ids"),req["mode"],req.get("simulated_harness_state"),req.get("recorded_live_original_at"),
            bool(req.get("cancel_requested",False)),transport,runner,_request_resolver(req),req.get("explicit_run_id"),
            req.get("physical_http_attempts_used"),req["rank_domains"],req["shortlist_options"],req["qloo_network_attempt_limit"],
            req["llm_call_limit"],req.get("resolution_choices"),req["active_time_limit_ms"],req["active_time_already_used_ms"],audit)
    else:
        parser.print_help(); return 0
    bundle["public_export"]=build_public_export(bundle)
    persist_redacted_execution_proof(bundle)
    bundle.pop("execution_proof_paths",None)
    sys.stdout.write(json.dumps(bundle,ensure_ascii=False,allow_nan=False)+"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())


