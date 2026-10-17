# The Taste-Matched Trailer — Qloo Cultural Intelligence Agent

**Built for the [Qloo Agentic Hackathon](https://qloo.devpost.com) ("Agents, but with taste")**
**License:** MIT (Open Source)

## Why This Exists (and Why It Cannot Work Without Qloo)

> *"If your submission would work the same without Qloo, you're building the wrong thing."*

When an independent author or small publisher wants to promote a book on BookTok (TikTok), Instagram Reels, YouTube Shorts, or Amazon KDP, generic LLMs fail at creative direction because **they only read the text in isolation** — they have zero empirical knowledge of **real-world cross-domain cultural taste**.

**The Taste-Matched Trailer** bridges manuscript analysis with the **Qloo Cultural Taste Graph (250M+ entities)** to act as an autonomous Cultural Director:
1. **Literary DNA Extraction:** Analyzes a manuscript's themes, era, emotional cadence (BPM), and chromatic palette.
2. **Qloo Seed Entity Resolution (`urn:entity:book`):** Anchors the manuscript against comparable literary works in Qloo's graph.
3. **Cross-Domain Taste Graph Traversal (`urn:entity:movie`, `urn:entity:artist`):** Queries Qloo for the exact films, directors, cinematographers, and soundtrack composers that readers of those seed books statistically over-index on.
4. **Audience Persona Clustering:** Identifies high-conversion reader cohorts and where they discover new books.
5. **Executable LTX-2.5 Book-Trailer Production Brief:** Synthesizes a 6-shot cinematic trailer brief (visual prompts, bilingual voiceover, sonic cues, and Qloo aesthetic anchors) ready for local video & voice rendering (`9:16` Vertical + `16:9` Widescreen).

---

## Quick Start

### 1. Interactive Web Application (Zero-Install)
Open `index.html` directly in any browser or serve locally:
```bash
python3 -m http.server 8080 --directory .
```
Then visit `http://localhost:8080`.

### 2. Python Agent CLI (with optional Live Qloo API Key)
```bash
# Run with verified Qloo Taste Graph profile and export an LTX-2.5 studio brief:
python3 taste_matched_trailer_agent.py \
  --profile le-horla-maupassant \
  --export-brief ./brief-horla-ltx25.json

# Run with a live Qloo API key (hackathon.api.qloo.com / api.qloo.com):
QLOO_API_KEY="your_qloo_key" python3 taste_matched_trailer_agent.py \
  --profile le-bronze-et-la-cendre \
  --export-brief ./brief-bronze-ltx25.json
```

---

## Included Case Studies

1. **Case 1 — *Le Horla* (Guy de Maupassant, 1887):**
   - **Qloo Seed Books:** *The Turn of the Screw*, *The Fall of the House of Usher*, *Rebecca*
   - **Qloo Cinema & Sonic Matches:** *The Lighthouse* (95%), *The Others* (93%), *Nosferatu* (91%) × Hildur Guðnadóttir (94%), Colin Stetson (90%)
   - **Rendered Output:** Full 40.25s `9:16` & `16:9` narrated trailer rendered via our local LTX-2.5 + Kyutai TTS studio pipeline.
2. **Case 2 — *Le Bronze et la Cendre* (Yann Abadie, 2026):**
   - **Qloo Seed Books:** *Hyperion*, *Memoirs of Hadrian*, *Dune*
   - **Qloo Cinema & Sonic Matches:** *Dune: Part Two* (96%), *Blade Runner 2049* (92%), *Rome* (89%) × Jóhann Jóhannsson (95%), Max Richter (92%)
