# The Taste-Matched Trailer — Qloo Cultural Intelligence Agent

**Built for the [Qloo Agentic Hackathon](https://qloo.devpost.com) ("Agents, but with taste")**  
**Live Hosted Demo:** [https://yannabadie.github.io/taste-matched-trailer/](https://yannabadie.github.io/taste-matched-trailer/)  
**Live Commercial Case Study (*Le Bronze et la Cendre*):** [https://yannabadie.github.io/taste-matched-trailer/le-bronze-et-la-cendre.html](https://yannabadie.github.io/taste-matched-trailer/le-bronze-et-la-cendre.html)  
**License:** MIT (Open Source)

## Why This Exists (and Why It Cannot Work Without Qloo)

> *"If your submission would work the same without Qloo, you're building the wrong thing."*

When an independent author or small publisher wants to promote a book on BookTok (TikTok), Instagram Reels, YouTube Shorts, or Amazon KDP, generic LLMs fail at creative direction because **they only read the text in isolation** — they have zero empirical knowledge of **real-world cross-domain cultural taste**.

**The Taste-Matched Trailer** bridges manuscript analysis with the **Qloo Cultural Taste Graph (250M+ entities)** to act as an autonomous Cultural Director:
1. **Literary DNA Extraction:** Analyzes a manuscript's themes, era, emotional cadence (BPM), and chromatic palette.
2. **Qloo Seed Entity Resolution (`urn:entity:book`):** Anchors the manuscript against comparable literary works in Qloo's graph.
3. **Cross-Domain Taste Graph Traversal (`urn:entity:movie`, `urn:entity:artist`):** Queries Qloo for the exact films, directors, cinematographers, and soundtrack composers that readers of those seed books statistically over-index on.
4. **Audience Persona Clustering:** Identifies high-conversion reader cohorts and where they discover new books.
5. **Executable LTX-2.5 Book-Trailer Production & Rendering:** Synthesizes a 6-shot cinematic trailer brief (visual prompts, bilingual voiceover, sonic cues, and Qloo aesthetic anchors) and renders the complete `16:9` Widescreen and `9:16` BookTok MP4 trailers locally using **LTX-2.5** and **Kyutai TTS**.

---

## Quick Start

### 1. Live Web Application & Embedded Video Outputs
Visit **[https://yannabadie.github.io/taste-matched-trailer/](https://yannabadie.github.io/taste-matched-trailer/)** (or serve locally with `python3 -m http.server 8080 --directory .`) to:
- Explore multi-hop Qloo Taste Graph traversals for both manuscripts.
- Stream the **real rendered book trailers** (`16:9 Landscape` and `9:16 Vertical BookTok`) directly in the browser.
- Visit the live storefront page (`le-bronze-et-la-cendre.html`) powered by the generated trailer.

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

## Included Case Studies & Rendered Video Assets (`assets/`)

1. **Case 1 — *Le Bronze et la Cendre* (Yann Abadie, 2026):**
   - **Qloo Seed Books:** *Hyperion*, *Memoirs of Hadrian*, *Dune*
   - **Qloo Cinema & Sonic Matches:** *Dune: Part Two* (96%), *Blade Runner 2049* (92%), *Rome* (89%) × Jóhann Jóhannsson (95%), Max Richter (92%)
   - **Rendered Output:** `assets/teaser-bronze-v1-16x9.mp4` (`16:9`) & `assets/teaser-bronze-v1.mp4` (`9:16` BookTok), 40.58s, 24 fps, narrated via Kyutai TTS.
2. **Case 2 — *Le Horla* (Guy de Maupassant, 1887):**
   - **Qloo Seed Books:** *The Turn of the Screw*, *The Fall of the House of Usher*, *Rebecca*
   - **Qloo Cinema & Sonic Matches:** *The Lighthouse* (95%), *The Others* (93%), *Nosferatu* (91%) × Hildur Guðnadóttir (94%), Colin Stetson (90%)
   - **Rendered Output:** `assets/teaser-horla-v1-16x9.mp4` (`16:9`) & `assets/teaser-horla-v1.mp4` (`9:16` BookTok), 40.25s, 24 fps, narrated via Kyutai TTS.
