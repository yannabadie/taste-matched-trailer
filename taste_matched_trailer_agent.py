#!/usr/bin/env python3
"""The Taste-Matched Trailer — Cultural Intelligence Agent powered by Qloo Taste API.

Built for the Qloo Agentic Hackathon (https://qloo.devpost.com).

Provenance & Verification Architecture:
- Offline Demo Mode (`api_key=None`):
  Returns `PRECOMPUTED_PROFILES[slug]` explicitly tagged with:
    `mode = "offline_precomputed_demo"`
    `qloo_api_verified = False`
    `data_provenance = "precomputed_reference_fixture"`
    `steps_completed = ["offline_fixture_loaded"]`
  Offline mode never claims that Qloo API steps were executed or verified.

- Live Verified Qloo API Mode (`api_key` provided):
  Executes live HTTP requests against Qloo's `/search` and `/v2/insights` (with `/insights`
  fallback) endpoints so that the API responses directly determine:
    1. `qloo_seed_books` (resolved book entities & match scores from Qloo)
    2. `qloo_cross_domain_graph.films_and_visual_aesthetic` (movie entities, affinity scores, rationales)
    3. `qloo_cross_domain_graph.soundtrack_and_composers` (artist entities, affinity scores, rationales)
    4. `qloo_cross_domain_graph.audience_personas` (share percentages & channels derived from live affinities)
    5. `trailer_shots` (`qloo_anchor`, `sonic_cue`, `visual_prompt`, and `qloo_source_entity_ids`
       dynamically synthesized from the top API-returned films, composers, and seed books)
  Sets `qloo_api_verified = True` and records `live_api_response_sha256` ONLY when live API
  responses were received and used to compute the outputs. If the API call fails, sets
  `qloo_api_verified = False` and `mode = "live_qloo_api_failed_fallback_to_demo"` (or raises
  an error when `strict_live=True`).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

QLOO_BASE_URLS = (
    "https://hackathon.api.qloo.com",
)

HttpGetJsonFn = Callable[[str, dict[str, str]], dict[str, Any]]


@dataclass
class CulturalEntity:
    name: str
    entity_id: str
    domain: str
    affinity_score: float
    rationale: str


@dataclass
class TrailerShot:
    shot_id: str
    duration_s: float
    visual_prompt: str
    voiceover_fr: str
    voiceover_en: str
    sonic_cue: str
    qloo_anchor: str


# Static reference fixtures used ONLY for offline demonstration when no live Qloo API key is provided.
PRECOMPUTED_PROFILES: dict[str, dict[str, Any]] = {
    "le-horla-maupassant": {
        "title": "Le Horla",
        "author": "Guy de Maupassant",
        "era_setting": "Normandie, France (1887) — Manoir isolé en bord de Seine",
        "seed_queries": [
            "The Turn of the Screw Henry James",
            "The Fall of the House of Usher Poe",
            "Rebecca Daphne du Maurier",
        ],
        "literary_dna": {
            "primary_themes": ["Dépossession psychologique", "Présence invisible", "Isolement sensoriel", "Folie rationnelle"],
            "emotional_arc": ["Sérénité domestique", "Doute matériel (l'eau bue)", "Terreur nocturne", "Absence du reflet", "Le feu ultime"],
            "pacing_tempo_bpm": 62,
            "color_palette": ["#0C0F1A", "#D8B982", "#4A5D6E", "#8B261D"],
        },
        "qloo_seed_books": [
            {"name": "The Turn of the Screw (Henry James)", "entity_id": "urn:entity:book:turn_of_the_screw", "match": 0.96, "source": "precomputed_fixture"},
            {"name": "The Fall of the House of Usher (E.A. Poe)", "entity_id": "urn:entity:book:house_of_usher", "match": 0.94, "source": "precomputed_fixture"},
            {"name": "Rebecca (Daphne du Maurier)", "entity_id": "urn:entity:book:rebecca_du_maurier", "match": 0.89, "source": "precomputed_fixture"},
        ],
        "qloo_cross_domain_graph": {
            "films_and_visual_aesthetic": [
                {
                    "name": "The Lighthouse (Robert Eggers, 2019)",
                    "entity_id": "urn:entity:movie:the_lighthouse_2019",
                    "affinity_score": 0.95,
                    "rationale": "[Offline Reference Fixture] Over-indexes among readers of 19th-century psychological gothic; dictates high-contrast chiaroscuro and claustrophobic framing.",
                    "source": "precomputed_fixture",
                },
                {
                    "name": "The Others (Alejandro Amenábar, 2001)",
                    "entity_id": "urn:entity:movie:the_others_2001",
                    "affinity_score": 0.93,
                    "rationale": "[Offline Reference Fixture] Shared audience affinity for fog-bound manor architecture, candlelit interiors, and unseen domestic intrusion.",
                    "source": "precomputed_fixture",
                },
                {
                    "name": "Nosferatu (Robert Eggers, 2024)",
                    "entity_id": "urn:entity:movie:nosferatu_2024",
                    "affinity_score": 0.91,
                    "rationale": "[Offline Reference Fixture] Strong visual taste overlap on nocturnal blue-slate dusk and tactile 19th-century Normandy/Baltic textures.",
                    "source": "precomputed_fixture",
                },
            ],
            "soundtrack_and_composers": [
                {
                    "name": "Hildur Guðnadóttir",
                    "entity_id": "urn:entity:artist:hildur_gudnadottir",
                    "affinity_score": 0.94,
                    "rationale": "[Offline Reference Fixture] Solo cello sub-bass drones and resonant acoustic tension preferred by this literary cohort.",
                    "source": "precomputed_fixture",
                },
                {
                    "name": "Colin Stetson",
                    "entity_id": "urn:entity:artist:colin_stetson",
                    "affinity_score": 0.90,
                    "rationale": "[Offline Reference Fixture] Breath-driven low woodwind pulses matching the nocturnal suffocation motif (Shot P3).",
                    "source": "precomputed_fixture",
                },
                {
                    "name": "Camille Saint-Saëns (Danse Macabre / Requiem)",
                    "entity_id": "urn:entity:artist:camille_saint_saens",
                    "affinity_score": 0.88,
                    "rationale": "[Offline Reference Fixture] Period-authentic French late-Romantic harmonic tension.",
                    "source": "precomputed_fixture",
                },
            ],
            "audience_personas": [
                {
                    "segment": "Gothic & Literary Horror Collectors (BookTok #DarkAcademia / #ClassicHorror)",
                    "share_pct": 46,
                    "channels": ["TikTok #DarkAcademia", "Letterboxd Gothic Lists", "Goodreads Weird Fiction"],
                    "source": "precomputed_fixture",
                },
                {
                    "segment": "A24 / Arthouse Psychological Thriller Viewers",
                    "share_pct": 34,
                    "channels": ["YouTube Video Essays", "MUBI Community", "Instagram Reels Cinema"],
                    "source": "precomputed_fixture",
                },
                {
                    "segment": "Francophone Audiobook & Classic Literature Listeners",
                    "share_pct": 20,
                    "channels": ["Amazon KDP FR", "Babelio", "France Culture Podcasts"],
                    "source": "precomputed_fixture",
                },
            ],
        },
        "trailer_shots": [
            {
                "shot_id": "horla-p1-maison",
                "duration_s": 5.9,
                "visual_prompt": "Wide establishing shot of a stone manor in Normandy at blue dusk, mist creeping across the lawn, warm amber candlelight behind tall windows, slow dolly-in, 35mm cinema grain.",
                "voiceover_fr": "Quelqu'un possède mon âme et la gouverne. Il est là, autour de moi, invisible.",
                "voiceover_en": "Someone possesses my soul and governs it. He is here, all around me, unseen.",
                "sonic_cue": "55 Hz cello drone + distant Seine river wind",
                "qloo_anchor": "The Others (2001) × Nosferatu (2024) dusk palette",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "horla-p2-verre",
                "duration_s": 5.9,
                "visual_prompt": "Macro close-up of a crystal carafe and a clear glass of water on a dark oak nightstand lit by a single candle; a faint concentric ripple disturbs the water surface by itself.",
                "voiceover_fr": "Cette nuit, on a bu toute l'eau de ma carafe. On a bu… et je n'ai rien entendu.",
                "voiceover_en": "Last night, someone drank all the water from my carafe. Someone drank... and I heard nothing.",
                "sonic_cue": "Subtle crystal resonance + held breath",
                "qloo_anchor": "Hildur Guðnadóttir tactile micro-foley",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "horla-p3-silhouette",
                "duration_s": 6.9,
                "visual_prompt": "Medium shot of a pale 19th-century man in a white linen shirt sitting on the edge of a rumpled bed at night, gripping his collar, staring into the dark corner as the shadow behind him subtly thickens.",
                "voiceover_fr": "Je sens qu'il s'accroupit sur ma poitrine, qu'il boit ma vie entre mes lèvres.",
                "voiceover_en": "I feel him crouching upon my chest, drinking my very life from between my lips.",
                "sonic_cue": "Colin Stetson low contrabass pulse (62 BPM)",
                "qloo_anchor": "The Lighthouse (2019) chiaroscuro portrait framing",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "horla-p4-seine",
                "duration_s": 5.9,
                "visual_prompt": "Atmospheric wide shot of a three-masted white Brazilian ship gliding silently down the Seine river through morning fog past Normandy poplars.",
                "voiceover_fr": "Un trois-mâts brésilien passait sur la Seine, tout blanc… et je l'ai salué sans savoir pourquoi.",
                "voiceover_en": "A white Brazilian three-master glided down the Seine... and I saluted it without knowing why.",
                "sonic_cue": "Muffled foghorn + eerie high string harmonic",
                "qloo_anchor": "19th-Century French Symbolist Landscape Aesthetic",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "horla-p5-miroir",
                "duration_s": 7.9,
                "visual_prompt": "Slow push-in onto a tall antique oval wooden mirror in a candlelit bedroom; the bed and candle in the background are reflected clearly, but the foreground space remains terrifyingly empty.",
                "voiceover_fr": "Je me suis dressé devant mon armoire à glace… et je ne me suis pas vu ! Mon image n'était pas dedans !",
                "voiceover_en": "I stood before my looking-glass... and I did not see myself! My reflection was gone!",
                "sonic_cue": "Rising dissonant string glissando cutting to dead silence",
                "qloo_anchor": "Classic Gothic Mirror Motif (Poe / James cohort)",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "horla-p6-carton",
                "duration_s": 7.8,
                "visual_prompt": "Exact typographic end-card on deep midnight #0C0F1A background with warm gold #D8B982 serif lettering: GUY DE MAUPASSANT — LE HORLA.",
                "voiceover_fr": "Alors… il va donc falloir que je me tue, moi ? Le Horla. Guy de Maupassant.",
                "voiceover_en": "Then... must I destroy myself to end him? The Horla. Guy de Maupassant.",
                "sonic_cue": "Low brass resolve + ember crackle fade-out",
                "qloo_anchor": "A24 / Studio Video Local Minimalist Title Card",
                "qloo_live_derived": False,
            },
        ],
    },
    "le-bronze-et-la-cendre": {
        "title": "Le Bronze et la Cendre",
        "author": "Yann Abadie",
        "era_setting": "An 2287 & Antiquité impériale — Archéologie orbitale, mémoire du pouvoir et Légion d'Airain",
        "seed_queries": [
            "Hyperion Dan Simmons",
            "Memoirs of Hadrian Marguerite Yourcenar",
            "Dune Frank Herbert",
            "Foundation Isaac Asimov",
        ],
        "literary_dna": {
            "primary_themes": ["Continuité tragique des empires", "Archéologie du futur (2287)", "Serment militaire et trahison", "Mémoire de bronze face à la cendre"],
            "emotional_arc": ["Vestige exhumé", "Tension politique sous la voûte", "Le poids de l'armure", "Fracture du serment", "Survie de la trace"],
            "pacing_tempo_bpm": 74,
            "color_palette": ["#0C0F1A", "#D8B982", "#8C583A", "#2C3545"],
        },
        "qloo_seed_books": [
            {"name": "Hyperion (Dan Simmons)", "entity_id": "urn:entity:book:hyperion_simmons", "match": 0.95, "source": "precomputed_fixture"},
            {"name": "Memoirs of Hadrian (Marguerite Yourcenar)", "entity_id": "urn:entity:book:memoires_d_hadrien", "match": 0.93, "source": "precomputed_fixture"},
            {"name": "Dune (Frank Herbert)", "entity_id": "urn:entity:book:dune_herbert", "match": 0.91, "source": "precomputed_fixture"},
            {"name": "Foundation (Isaac Asimov)", "entity_id": "urn:entity:book:foundation_asimov", "match": 0.89, "source": "precomputed_fixture"},
        ],
        "qloo_cross_domain_graph": {
            "films_and_visual_aesthetic": [
                {
                    "name": "Dune: Part Two (Denis Villeneuve, 2024)",
                    "entity_id": "urn:entity:movie:dune_part_two",
                    "affinity_score": 0.96,
                    "rationale": "[Offline Reference Fixture] Readers combining literary antiquity with hard SF over-index on Villeneuve's monolithic brutalist framing and bronze/ochre dust palettes.",
                    "source": "precomputed_fixture",
                },
                {
                    "name": "Blade Runner 2049 (Denis Villeneuve, 2017)",
                    "entity_id": "urn:entity:movie:blade_runner_2049",
                    "affinity_score": 0.92,
                    "rationale": "[Offline Reference Fixture] High affinity on tactile relic examination scenes, museum-like silence, and amber-lit shadow geometry.",
                    "source": "precomputed_fixture",
                },
                {
                    "name": "Rome (HBO Series, Bruno Heller)",
                    "entity_id": "urn:entity:tv:rome_hbo",
                    "affinity_score": 0.89,
                    "rationale": "[Offline Reference Fixture] Strong overlap on oil-lamp antiquity textures, military insignia, and political stoicism.",
                    "source": "precomputed_fixture",
                },
            ],
            "soundtrack_and_composers": [
                {
                    "name": "Jóhann Jóhannsson",
                    "entity_id": "urn:entity:artist:johann_johannsson",
                    "affinity_score": 0.95,
                    "rationale": "[Offline Reference Fixture] Brass-and-organ slow-burn motifs bridging ancient liturgy and futuristic minimalism.",
                    "source": "precomputed_fixture",
                },
                {
                    "name": "Max Richter",
                    "entity_id": "urn:entity:artist:max_richter",
                    "affinity_score": 0.92,
                    "rationale": "[Offline Reference Fixture] Elegiac strings ('On the Nature of Daylight' cohort) matching the philosophical weight of Memoirs of Hadrian readers.",
                    "source": "precomputed_fixture",
                },
                {
                    "name": "Wardruna / Einar Selvik",
                    "entity_id": "urn:entity:artist:wardruna",
                    "affinity_score": 0.86,
                    "rationale": "[Offline Reference Fixture] Bronze horn and ritual percussion textures over-indexed by historical-mythological SF readers.",
                    "source": "precomputed_fixture",
                },
            ],
            "audience_personas": [
                {
                    "segment": "Literary & Philosophical Sci-Fi Readers (Hyperion / Dune / Yourcenar crossover)",
                    "share_pct": 48,
                    "channels": ["Amazon KDP SF Historique", "Babelio Imaginaire", "Reddit r/PrintSF & r/SciFi"],
                    "source": "precomputed_fixture",
                },
                {
                    "segment": "Antiquity & Civilizational History Enthusiasts",
                    "share_pct": 32,
                    "channels": ["YouTube Histoire/Archéologie", "Podcasts Antiquité", "Twitter/X Histoire"],
                    "source": "precomputed_fixture",
                },
                {
                    "segment": "Cinematic Speculative Fiction & Worldbuilding Fans",
                    "share_pct": 20,
                    "channels": ["BookTok #SFFR", "Instagram Reels Lecture", "Substack Essais"],
                    "source": "precomputed_fixture",
                },
            ],
        },
        "trailer_shots": [
            {
                "shot_id": "bronze-p1-lampe",
                "duration_s": 6.0,
                "visual_prompt": "Macro cinematic shot of an ancient verdigris bronze Roman oil lamp resting on dark volcanic ash; a warm flame flickers as fine ash particles drift upward in slow motion.",
                "voiceover_fr": "En 2287, on croyait les empires éteints. Il ne restait que le bronze… et la cendre.",
                "voiceover_en": "In 2287, they believed empires were extinct. Only bronze remained... and ash.",
                "sonic_cue": "Jóhannsson-style low bronze horn resonance + soft ash wind",
                "qloo_anchor": "Blade Runner 2049 relic lighting × Rome oil-lamp texture",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "bronze-p2-medaillon",
                "duration_s": 6.0,
                "visual_prompt": "Close-up of gloved archivist hands brushing grey ash off a fractured bronze military medallion bearing an imperial eagle and Latin-futuristic coordinates.",
                "voiceover_fr": "Sous la poussière des archives orbitales, un serment vieux de deux millénaires refait surface.",
                "voiceover_en": "Beneath the dust of orbital archives, a two-thousand-year-old oath resurfaces.",
                "sonic_cue": "Tactile stone/metal brush + sub-bass pulse",
                "qloo_anchor": "Hyperion / Dune archaeological mystery motif",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "bronze-p3-voute",
                "duration_s": 7.0,
                "visual_prompt": "Wide low-angle shot inside a monumental brutalist vault in 2287 where shafts of amber light cut through cold slate shadow onto a solitary silhouette examining a holographic stele.",
                "voiceover_fr": "Car les machines changent de siècle, mais la mécanique du pouvoir garde le même visage.",
                "voiceover_en": "For machines change centuries, yet the machinery of power keeps the very same face.",
                "sonic_cue": "Max Richter elegiac cello motif enters (74 BPM)",
                "qloo_anchor": "Dune: Part Two monolithic architectural scale",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "bronze-p4-legion",
                "duration_s": 6.5,
                "visual_prompt": "Medium shot of a commander in weathered bronze-and-carbon armor standing at the threshold of a wind-swept stone terrace at dusk, embers drifting past his motionless profile.",
                "voiceover_fr": "Quand la Légion d'Airain réclame son dû, nul ne choisit impunément son camp.",
                "voiceover_en": "When the Brazen Legion claims its debt, no one chooses a side with impunity.",
                "sonic_cue": "Deep ritual drum impact + rising brass chord",
                "qloo_anchor": "Memoirs of Hadrian stoic portrait × Villeneuve palette",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "bronze-p5-regard",
                "duration_s": 6.5,
                "visual_prompt": "Extreme close-up on the protagonist's eyes reflecting a warm amber flame in the darkness, slow push-in as the flame steadies.",
                "voiceover_fr": "Que reste-t-il d'un homme lorsque l'Histoire efface jusqu'à son nom ?",
                "voiceover_en": "What remains of a man when History erases even his name?",
                "sonic_cue": "High string harmonic suspended over silence",
                "qloo_anchor": "High-retention BookTok emotional close-up",
                "qloo_live_derived": False,
            },
            {
                "shot_id": "bronze-p6-carton",
                "duration_s": 8.0,
                "visual_prompt": "Exact typographic end-card on #0C0F1A midnight background with #D8B982 antique gold serif typography: YANN ABADIE — LE BRONZE ET LA CENDRE.",
                "voiceover_fr": "Le Bronze et la Cendre. Un roman de Yann Abadie.",
                "voiceover_en": "Bronze and Ash. A novel by Yann Abadie.",
                "sonic_cue": "Full orchestral brass & cello resolve",
                "qloo_anchor": "Direct-to-Reader Edition & KDP Launch Card",
                "qloo_live_derived": False,
            },
        ],
    },
}


def _default_http_get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Default HTTP GET JSON transport with 8-second timeout."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def _extract_entities_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extracts the list of entity objects from Qloo `/search`, `/v2/insights`, or `/insights` responses."""
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("results"), dict):
        inner = payload["results"]
        for key in ("entities", "items", "results"):
            if isinstance(inner.get(key), list):
                return inner[key]
    for key in ("results", "entities", "items", "data"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
    return []


def _extract_score_with_provenance(entity: dict[str, Any]) -> tuple[float | None, str]:
    """Extracts the exact numeric affinity score returned by Qloo without clamping or rank-based fallback.

    Popularity is never treated as an affinity score.
    Returns `(score, field_source)`. If no numeric affinity score exists in the Qloo entity payload,
    returns `(None, "missing_in_qloo_payload")`.
    """
    candidates: list[tuple[str, Any]] = []
    query_block = entity.get("query")
    if isinstance(query_block, dict):
        candidates.append(("query.affinity", query_block.get("affinity")))
    candidates.extend(
        [
            ("affinity_score", entity.get("affinity_score")),
            ("affinity", entity.get("affinity")),
            ("match", entity.get("match")),
        ]
    )
    for field_name, raw in candidates:
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return float(raw), field_name
    return None, "missing_in_qloo_payload"


def _format_score_label(score: float | None, prefix: str = "Qloo score") -> str:
    if score is None:
        return f"{prefix}: unrated in payload"
    return f"{prefix}: {score:.4g}"


def _extract_entity_id(entity: dict[str, Any], default_prefix: str) -> str | None:
    """Extracts a non-empty entity ID from a Qloo payload, or returns None if missing (never fabricates IDs)."""
    raw_val = entity.get("entity_id") or entity.get("id")
    if raw_val is None:
        return None
    raw_id = str(raw_val).strip()
    if not raw_id:
        return None
    if not raw_id.startswith("urn:entity:") and not raw_id.startswith("urn:tag:") and not raw_id.startswith("urn:demographics:"):
        return f"{default_prefix}:{raw_id}"
    return raw_id


def _extract_tags_summary(entity: dict[str, Any]) -> str:
    tags = entity.get("tags") or entity.get("disambiguation") or entity.get("properties", {}).get("genre")
    if isinstance(tags, list) and tags:
        names = [
            str(t.get("name") if isinstance(t, dict) else t)
            for t in tags[:3]
            if (t.get("name") if isinstance(t, dict) else t)
        ]
        if names:
            return ", ".join(names)
    if isinstance(tags, str) and tags.strip():
        return tags.strip()
    return "cross-domain taste co-affinity"


def query_qloo_endpoint(
    api_key: str,
    path_and_query: str,
    http_get_json: HttpGetJsonFn | None = None,
    errors_out: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Queries Qloo endpoints across configured base URLs and returns `(entities, raw_payload)`."""
    transport = http_get_json or _default_http_get_json
    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
    }
    for base in QLOO_BASE_URLS:
        url = f"{base}{path_and_query}"
        try:
            payload = transport(url, headers)
            entities = _extract_entities_from_payload(payload)
            if entities:
                return entities, payload
            if errors_out is not None:
                errors_out.append(f"{url} -> HTTP 200 (0 entities returned)")
        except urllib.error.HTTPError as exc:
            if errors_out is not None:
                errors_out.append(f"{url} -> HTTP {exc.code}")
        except Exception as exc:
            if errors_out is not None:
                errors_out.append(f"{url} -> {type(exc).__name__}: {exc}")
    return [], None


def query_qloo_live(
    api_key: str,
    query_text: str,
    entity_type: str = "urn:entity:movie",
    http_get_json: HttpGetJsonFn | None = None,
    errors_out: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Queries Qloo `/search` for a given query string and entity type."""
    params = urllib.parse.urlencode({"query": query_text, "types": entity_type, "take": 5})
    entities, _ = query_qloo_endpoint(
        api_key=api_key,
        path_and_query=f"/search?{params}",
        http_get_json=http_get_json,
        errors_out=errors_out,
    )
    return entities


def query_qloo_insights_live(
    api_key: str,
    seed_entity_ids: list[str],
    target_entity_type: str,
    fallback_query: str,
    http_get_json: HttpGetJsonFn | None = None,
    errors_out: list[str] | None = None,
    strict_live: bool = False,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """Queries Qloo `/v2/insights` seeded by resolved book entities.

    When `strict_live=False`, may fall back to legacy `/insights` or `/search` for discovery,
    labeling the endpoint accurately (`qloo_legacy_insights` or `qloo_live_search`) so that
    only `/v2/insights` can qualify as `qloo_api_verified = True`.
    """
    raw_payloads: list[dict[str, Any]] = []
    clean_seeds = [s.split(":")[-1] if s.startswith("urn:entity:") else s for s in seed_entity_ids if s]
    seed_param = ",".join(clean_seeds[:4])

    if not seed_param:
        if errors_out is not None:
            errors_out.append(f"Skipped /v2/insights for {target_entity_type}: no resolved seed book entity IDs")
        if strict_live:
            return [], "none", raw_payloads
    else:
        v2_path = f"/v2/insights?{urllib.parse.urlencode({'filter.type': target_entity_type, 'signal.interests.entities': seed_param, 'take': 5})}"
        entities, payload = query_qloo_endpoint(
            api_key=api_key,
            path_and_query=v2_path,
            http_get_json=http_get_json,
            errors_out=errors_out,
        )
        if payload is not None:
            raw_payloads.append(payload)
        if entities:
            return entities, "qloo_v2_insights", raw_payloads

        if strict_live:
            return [], "none", raw_payloads

        legacy_path = f"/insights?{urllib.parse.urlencode({'filter.type': target_entity_type, 'signal.interests.entities': seed_param, 'take': 5})}"
        entities, payload = query_qloo_endpoint(
            api_key=api_key,
            path_and_query=legacy_path,
            http_get_json=http_get_json,
            errors_out=errors_out,
        )
        if payload is not None:
            raw_payloads.append(payload)
        if entities:
            return entities, "qloo_legacy_insights", raw_payloads

    if strict_live:
        return [], "none", raw_payloads

    search_params = urllib.parse.urlencode({"query": fallback_query, "types": target_entity_type, "take": 5})
    entities, payload = query_qloo_endpoint(
        api_key=api_key,
        path_and_query=f"/search?{search_params}",
        http_get_json=http_get_json,
        errors_out=errors_out,
    )
    if payload is not None:
        raw_payloads.append(payload)
    if entities:
        return entities, "qloo_live_search", raw_payloads

    return [], "none", raw_payloads


def compute_audience_personas_from_qloo(
    slug: str,
    seed_books: list[dict[str, Any]],
    films: list[dict[str, Any]],
    composers: list[dict[str, Any]],
    demographic_entities: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Builds editorial audience cohort proposals anchored on Qloo entities without fabricating `share_pct`.

    - If Qloo returned explicit demographic/tag entities with a `share_pct` or `percentage` field,
      that exact numeric value and its field name are preserved.
    - Otherwise, `share_pct` is set to `None` with `share_pct_provenance = "not_provided_by_qloo_api"`
      and the verbatim `qloo_affinity` of each domain's top entity is reported alongside editorial
      channel proposals (`channel_provenance = "editorial_proposal_not_qloo_clustering"`).
    """
    if demographic_entities:
        personas: list[dict[str, Any]] = []
        for idx, d_ent in enumerate(demographic_entities[:3]):
            ent_id = _extract_entity_id(d_ent, "urn:demographics:cluster")
            if not ent_id:
                continue
            q_block = d_ent.get("query") if isinstance(d_ent.get("query"), dict) else {}
            raw_pct = d_ent.get("share_pct") if d_ent.get("share_pct") is not None else d_ent.get("percentage", q_block.get("share_pct"))
            pct_val = float(raw_pct) if isinstance(raw_pct, (int, float)) and not isinstance(raw_pct, bool) else None
            score_val, score_src = _extract_score_with_provenance(d_ent)
            personas.append(
                {
                    "segment": str(d_ent.get("name") or d_ent.get("id") or f"Qloo Audience Cluster #{idx + 1}"),
                    "entity_id": ent_id,
                    "share_pct": pct_val,
                    "share_pct_provenance": "qloo_api_demographic_field" if pct_val is not None else "not_provided_by_qloo_api",
                    "qloo_affinity": score_val,
                    "qloo_score_field_source": score_src,
                    "channels": list(d_ent.get("channels") or []),
                    "source": "qloo_live_api",
                }
            )
        if personas:
            return personas

    top_book = seed_books[0] if seed_books else {"name": "Seed Book", "entity_id": "urn:entity:book:0", "match": None, "score_field_source": "missing_in_qloo_payload"}
    top_film = films[0] if films else {"name": "Top Film", "entity_id": "urn:entity:movie:0", "affinity_score": None, "score_field_source": "missing_in_qloo_payload"}
    top_comp = composers[0] if composers else {"name": "Top Composer", "entity_id": "urn:entity:artist:0", "affinity_score": None, "score_field_source": "missing_in_qloo_payload"}

    return [
        {
            "segment": f"Editorial Literary Cohort Proposal anchored on {top_book['name']}",
            "anchor_entity_id": top_book["entity_id"],
            "share_pct": None,
            "share_pct_provenance": "not_provided_by_qloo_api",
            "qloo_affinity": top_book.get("match"),
            "qloo_score_field_source": top_book.get("score_field_source", "missing_in_qloo_payload"),
            "channels": ["BookTok", "Goodreads", "Babelio"] if slug == "le-horla-maupassant" else ["Amazon KDP", "Babelio Imaginaire", "Reddit r/PrintSF"],
            "channel_provenance": "editorial_proposal_not_qloo_clustering",
            "source": "qloo_live_entity_affinity_only",
        },
        {
            "segment": f"Editorial Cinema Cohort Proposal anchored on {top_film['name']}",
            "anchor_entity_id": top_film["entity_id"],
            "share_pct": None,
            "share_pct_provenance": "not_provided_by_qloo_api",
            "qloo_affinity": top_film.get("affinity_score"),
            "qloo_score_field_source": top_film.get("score_field_source", "missing_in_qloo_payload"),
            "channels": ["Letterboxd", "MUBI", "YouTube Film Essays"],
            "channel_provenance": "editorial_proposal_not_qloo_clustering",
            "source": "qloo_live_entity_affinity_only",
        },
        {
            "segment": f"Editorial Sonic Cohort Proposal anchored on {top_comp['name']}",
            "anchor_entity_id": top_comp["entity_id"],
            "share_pct": None,
            "share_pct_provenance": "not_provided_by_qloo_api",
            "qloo_affinity": top_comp.get("affinity_score"),
            "qloo_score_field_source": top_comp.get("score_field_source", "missing_in_qloo_payload"),
            "channels": ["Spotify Soundtrack Curators", "Bandcamp", "YouTube Shorts Audio"],
            "channel_provenance": "editorial_proposal_not_qloo_clustering",
            "source": "qloo_live_entity_affinity_only",
        },
    ]


def synthesize_trailer_shots_from_qloo_graph(
    base_shots: list[dict[str, Any]],
    seed_books: list[dict[str, Any]],
    films: list[dict[str, Any]],
    composers: list[dict[str, Any]],
    pacing_bpm: int,
) -> list[dict[str, Any]]:
    """Dynamically rewrites shot `qloo_anchor`, `sonic_cue`, and `visual_prompt` from live Qloo entities."""
    f0 = films[0] if len(films) > 0 else {"name": "Primary Qloo Film", "entity_id": "urn:entity:movie:0", "affinity_score": None}
    f1 = films[1] if len(films) > 1 else f0
    f2 = films[2] if len(films) > 2 else f1

    c0 = composers[0] if len(composers) > 0 else {"name": "Primary Qloo Composer", "entity_id": "urn:entity:artist:0", "affinity_score": None}
    c1 = composers[1] if len(composers) > 1 else c0
    c2 = composers[2] if len(composers) > 2 else c1

    b0 = seed_books[0] if len(seed_books) > 0 else {"name": "Primary Qloo Book", "entity_id": "urn:entity:book:0", "match": None}
    b1 = seed_books[1] if len(seed_books) > 1 else b0

    shot_recipes = [
        {
            "anchor": f"{f0['name']} ({_format_score_label(f0.get('affinity_score'), 'Qloo match')}) × {f1['name']} visual grading",
            "sonic": f"{c0['name']}-inspired low drone ({_format_score_label(c0.get('affinity_score'), 'Qloo affinity')}) + atmospheric wind",
            "style_suffix": f"Visual aesthetic calibrated to Qloo twin film {f0['name']} ({f0['entity_id']}).",
            "sources": [f0["entity_id"], f1["entity_id"], c0["entity_id"]],
        },
        {
            "anchor": f"{c0['name']} tactile micro-foley × {b0['name']} tension motif",
            "sonic": f"{c0['name']} close-mic acoustic resonance + suspended breath",
            "style_suffix": f"Tactile close-up framed for the {b0['name']} reader cohort ({b0['entity_id']}).",
            "sources": [c0["entity_id"], b0["entity_id"]],
        },
        {
            "anchor": f"{f1['name']} ({_format_score_label(f1.get('affinity_score'), 'Qloo match')}) framing & shadow geometry",
            "sonic": f"{c1['name']} rhythmic pulse at {pacing_bpm} BPM ({_format_score_label(c1.get('affinity_score'), 'Qloo affinity')})",
            "style_suffix": f"Lighting and shadow contrast anchored in {f1['name']} ({f1['entity_id']}).",
            "sources": [f1["entity_id"], c1["entity_id"]],
        },
        {
            "anchor": f"{b1['name']} narrative motif × {f2['name']} atmospheric palette",
            "sonic": f"{c2['name']} harmonic texture ({_format_score_label(c2.get('affinity_score'), 'Qloo affinity')}) + deep sub-bass impact",
            "style_suffix": f"Wide environmental composition echoing {f2['name']} ({f2['entity_id']}).",
            "sources": [b1["entity_id"], f2["entity_id"], c2["entity_id"]],
        },
        {
            "anchor": f"High-retention close-up for {b0['name']} × {f0['name']} crossover audience",
            "sonic": f"{c1['name']} high string harmonic suspended over silence",
            "style_suffix": f"Emotional close-up tuned to {f0['name']} & {b0['name']} shared taste cluster.",
            "sources": [b0["entity_id"], f0["entity_id"], c1["entity_id"]],
        },
        {
            "anchor": f"Launch Title Card — {f0['name']} / {c0['name']} taste-matched edition",
            "sonic": f"Full {c0['name']} & {c1['name']} brass/cello resolve",
            "style_suffix": f"End-card sonic and visual resolve anchored by {c0['name']} ({c0['entity_id']}).",
            "sources": [f0["entity_id"], c0["entity_id"], c1["entity_id"]],
        },
    ]

    synthesized: list[dict[str, Any]] = []
    for idx, shot in enumerate(base_shots):
        new_shot = copy.deepcopy(shot)
        recipe = shot_recipes[idx % len(shot_recipes)]
        new_shot["qloo_anchor"] = recipe["anchor"]
        new_shot["sonic_cue"] = recipe["sonic"]
        new_shot["visual_prompt"] = f"{shot['visual_prompt']} [{recipe['style_suffix']}]"
        new_shot["qloo_live_derived"] = True
        new_shot["qloo_source_entity_ids"] = recipe["sources"]
        synthesized.append(new_shot)
    return synthesized


def run_agent(
    slug: str,
    api_key: str | None = None,
    export_ltx_brief: Path | None = None,
    http_get_json: HttpGetJsonFn | None = None,
    strict_live: bool = False,
) -> dict[str, Any]:
    """Runs the Taste-Matched Trailer agent.

    - Without `api_key`: returns the offline precomputed demo fixture with `qloo_api_verified = False`.
    - With `api_key`: queries Qloo's live endpoints and recomputes `qloo_seed_books`,
      `qloo_cross_domain_graph` (movies, composers, audience personas), and `trailer_shots`
      (`qloo_anchor`, `sonic_cue`, `visual_prompt`) directly from the API responses.
    """
    if slug not in PRECOMPUTED_PROFILES:
        raise ValueError(f"Unknown profile {slug!r}. Available: {list(PRECOMPUTED_PROFILES)}")

    profile = copy.deepcopy(PRECOMPUTED_PROFILES[slug])
    clean_key = (api_key or "").strip()

    if not clean_key:
        if strict_live:
            raise RuntimeError("strict_live=True requires a non-empty Qloo API key.")
        profile["agent_execution"] = {
            "mode": "offline_precomputed_demo",
            "qloo_api_verified": False,
            "data_provenance": "precomputed_reference_fixture",
            "steps_completed": [
                "offline_fixture_loaded",
            ],
            "verification_note": (
                "No QLOO_API_KEY provided. Output uses static precomputed reference fixtures "
                "for demonstration only; no live Qloo API call was executed."
            ),
        }
    else:
        api_errors: list[str] = []
        raw_responses_digest_material: list[Any] = []

        # Step 1: Resolve seed book entities via live Qloo `/search`
        seed_queries: list[str] = profile.get("seed_queries") or [profile["title"]]
        live_seed_books: list[dict[str, Any]] = []
        seen_book_ids: set[str] = set()
        for seed_q in seed_queries:
            hits = query_qloo_live(
                clean_key,
                seed_q,
                entity_type="urn:entity:book",
                http_get_json=http_get_json,
                errors_out=api_errors,
            )
            if hits:
                raw_responses_digest_material.append({"step": "seed_book_search", "query": seed_q, "hits": hits[:2]})
                for hit in hits:
                    ent_id = _extract_entity_id(hit, "urn:entity:book")
                    if not ent_id:
                        api_errors.append(f"Book search hit for {seed_q!r} missing entity_id in Qloo payload")
                        continue
                    if ent_id not in seen_book_ids:
                        seen_book_ids.add(ent_id)
                        score_val, score_src = _extract_score_with_provenance(hit)
                        live_seed_books.append(
                            {
                                "name": str(hit.get("name") or seed_q),
                                "entity_id": ent_id,
                                "match": score_val,
                                "score_field_source": score_src,
                                "source": "qloo_live_api",
                            }
                        )
                        break

        seed_entity_ids = [b["entity_id"] for b in live_seed_books]
        theme_fallback_query = " ".join(profile["literary_dna"]["primary_themes"][:2])

        # Step 2: Fetch cross-domain movie affinities from Qloo `/v2/insights`
        movie_hits, movie_endpoint_used, movie_payloads = query_qloo_insights_live(
            api_key=clean_key,
            seed_entity_ids=seed_entity_ids,
            target_entity_type="urn:entity:movie",
            fallback_query=theme_fallback_query,
            http_get_json=http_get_json,
            errors_out=api_errors,
            strict_live=strict_live,
        )
        if movie_payloads:
            raw_responses_digest_material.append({"step": "movie_insights", "payloads": movie_payloads})

        live_films: list[dict[str, Any]] = []
        for idx, m_hit in enumerate(movie_hits[:3]):
            ent_id = _extract_entity_id(m_hit, "urn:entity:movie")
            if not ent_id:
                api_errors.append(f"Movie hit #{idx + 1} missing entity_id in Qloo payload")
                continue
            score_val, score_src = _extract_score_with_provenance(m_hit)
            tags_summary = _extract_tags_summary(m_hit)
            live_films.append(
                {
                    "name": str(m_hit.get("name") or f"Qloo Film #{idx + 1}"),
                    "entity_id": ent_id,
                    "affinity_score": score_val,
                    "score_field_source": score_src,
                    "rationale": (
                        f"Live Qloo API ({movie_endpoint_used}, { _format_score_label(score_val, score_src) }) "
                        f"seeded by {', '.join(seed_entity_ids[:2]) or 'manuscript themes'} "
                        f"[{tags_summary}]."
                    ),
                    "source": "qloo_live_api",
                }
            )

        # Step 3: Fetch cross-domain composer/artist affinities from Qloo `/v2/insights`
        artist_hits, artist_endpoint_used, artist_payloads = query_qloo_insights_live(
            api_key=clean_key,
            seed_entity_ids=seed_entity_ids,
            target_entity_type="urn:entity:artist",
            fallback_query=f"soundtrack composer {profile['title']}",
            http_get_json=http_get_json,
            errors_out=api_errors,
            strict_live=strict_live,
        )
        if artist_payloads:
            raw_responses_digest_material.append({"step": "artist_insights", "payloads": artist_payloads})

        live_composers: list[dict[str, Any]] = []
        for idx, a_hit in enumerate(artist_hits[:3]):
            ent_id = _extract_entity_id(a_hit, "urn:entity:artist")
            if not ent_id:
                api_errors.append(f"Artist hit #{idx + 1} missing entity_id in Qloo payload")
                continue
            score_val, score_src = _extract_score_with_provenance(a_hit)
            tags_summary = _extract_tags_summary(a_hit)
            live_composers.append(
                {
                    "name": str(a_hit.get("name") or f"Qloo Artist #{idx + 1}"),
                    "entity_id": ent_id,
                    "affinity_score": score_val,
                    "score_field_source": score_src,
                    "rationale": (
                        f"Live Qloo API ({artist_endpoint_used}, { _format_score_label(score_val, score_src) }) "
                        f"[{tags_summary}]."
                    ),
                    "source": "qloo_live_api",
                }
            )

        # Strict qualification: only mark `qloo_api_verified = True` if all 3 live domains returned
        # entities with valid IDs AND both movie and artist came from `/v2/insights`.
        insights_verified = (
            movie_endpoint_used == "qloo_v2_insights" and artist_endpoint_used == "qloo_v2_insights"
        )
        if live_seed_books and live_films and live_composers and insights_verified:
            profile["qloo_seed_books"] = live_seed_books
            profile["qloo_cross_domain_graph"]["films_and_visual_aesthetic"] = live_films
            profile["qloo_cross_domain_graph"]["soundtrack_and_composers"] = live_composers
            profile["qloo_cross_domain_graph"]["audience_personas"] = compute_audience_personas_from_qloo(
                slug=slug,
                seed_books=live_seed_books,
                films=live_films,
                composers=live_composers,
            )
            profile["trailer_shots"] = synthesize_trailer_shots_from_qloo_graph(
                base_shots=profile["trailer_shots"],
                seed_books=live_seed_books,
                films=live_films,
                composers=live_composers,
                pacing_bpm=int(profile["literary_dna"]["pacing_tempo_bpm"]),
            )
            digest = hashlib.sha256(
                json.dumps(raw_responses_digest_material, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            profile["agent_execution"] = {
                "mode": "live_qloo_api_verified",
                "qloo_api_verified": True,
                "data_provenance": "qloo_live_api_responses",
                "score_handling": "verbatim_from_qloo_payload_no_clamping_or_rank_fallback",
                "audience_share_handling": "no_fabricated_demographic_percentages_when_absent_from_qloo",
                "movie_endpoint_used": movie_endpoint_used,
                "artist_endpoint_used": artist_endpoint_used,
                "live_qloo_probe_results": len(live_seed_books) + len(live_films) + len(live_composers),
                "live_api_response_sha256": digest,
                "fields_determined_by_api": [
                    "qloo_seed_books",
                    "qloo_cross_domain_graph.films_and_visual_aesthetic",
                    "qloo_cross_domain_graph.soundtrack_and_composers",
                    "qloo_cross_domain_graph.audience_personas",
                    "trailer_shots[*].qloo_anchor",
                    "trailer_shots[*].sonic_cue",
                    "trailer_shots[*].visual_prompt",
                ],
                "steps_completed": [
                    "1_profile_seed_selection",
                    "2_qloo_live_seed_entity_resolution",
                    "3_qloo_live_cross_domain_affinity_matrix",
                    "4_editorial_cohort_mapping_from_entity_affinities",
                    "5_qloo_live_ltx25_shot_brief_synthesis",
                ],
            }
        else:
            if strict_live:
                raise RuntimeError(
                    f"Live Qloo API verification failed (seed_books={len(live_seed_books)}, "
                    f"films={len(live_films)} via {movie_endpoint_used}, "
                    f"composers={len(live_composers)} via {artist_endpoint_used}). Errors: {api_errors}"
                )
            profile["agent_execution"] = {
                "mode": "live_qloo_api_failed_fallback_to_demo",
                "qloo_api_verified": False,
                "data_provenance": "precomputed_reference_fixture_after_api_error",
                "movie_endpoint_used": movie_endpoint_used,
                "artist_endpoint_used": artist_endpoint_used,
                "live_qloo_probe_results": len(live_seed_books) + len(live_films) + len(live_composers),
                "api_errors": api_errors[:10],
                "steps_completed": [
                    "live_qloo_api_attempt_failed",
                    "offline_fixture_fallback_loaded",
                ],
                "verification_note": (
                    "A Qloo API key was provided, but live /v2/insights endpoints did not return complete "
                    "cross-domain entities with valid IDs. Falling back to static offline demo fixtures (`qloo_api_verified = False`)."
                ),
            }

    if export_ltx_brief:
        ltx_brief = {
            "id": f"qloo-taste-trailer-{slug}",
            "title": f"{profile['title']} — Qloo Taste-Matched Trailer ({profile['author']})",
            "format": {"width": 576, "height": 1024, "fps": 24},
            "qloo_api_verified": profile["agent_execution"]["qloo_api_verified"],
            "data_provenance": profile["agent_execution"]["data_provenance"],
            "qloo_cultural_positioning": profile["qloo_cross_domain_graph"],
            "shots": [
                {
                    "id": s["shot_id"],
                    "duration_s": s["duration_s"],
                    "prompt": s["visual_prompt"],
                    "voiceover_fr": s["voiceover_fr"],
                    "voiceover_en": s["voiceover_en"],
                    "sonic_cue": s["sonic_cue"],
                    "qloo_anchor": s["qloo_anchor"],
                    "qloo_live_derived": s.get("qloo_live_derived", False),
                    "qloo_source_entity_ids": s.get("qloo_source_entity_ids", []),
                }
                for s in profile["trailer_shots"]
            ],
        }
        export_ltx_brief.parent.mkdir(parents=True, exist_ok=True)
        export_ltx_brief.write_text(json.dumps(ltx_brief, indent=2, ensure_ascii=False), encoding="utf-8")

    return profile


def main() -> None:
    p = argparse.ArgumentParser(description="The Taste-Matched Trailer — Qloo Cultural Intelligence Agent")
    p.add_argument("--profile", default="le-horla-maupassant", choices=list(PRECOMPUTED_PROFILES.keys()))
    p.add_argument("--api-key", default=os.environ.get("QLOO_API_KEY"), help="Optional Qloo API Key")
    p.add_argument("--export-brief", type=Path, help="Export StudioVideoLocal LTX-2.5 brief JSON")
    p.add_argument(
        "--strict-live",
        action="store_true",
        help="Fail with an error if QLOO_API_KEY is missing or if live Qloo API calls do not return complete entities",
    )
    args = p.parse_args()

    result = run_agent(
        args.profile,
        api_key=args.api_key,
        export_ltx_brief=args.export_brief,
        strict_live=args.strict_live,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
