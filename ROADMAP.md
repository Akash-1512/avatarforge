# contentforge — Engineering Roadmap

**From talking-head backend to production-grade AI film pipeline.**
Status: foundation complete (v1.10.0). This document is the complete plan from
here to a shipped v2 content-creation platform. Costs verified June 2026.

---

## 1. The thesis

Give the platform a person (photo, uploaded video, or live capture) and a brief,
and it produces a finished short — reel, cinematic scene, or short film — with that
person rendered as a reusable digital character in the style they choose
(realistic, anime, Pixar-3D, and more), voiced, scored, captioned, and assembled.
Every output is checked against the brief by an agentic quality loop that
re-renders until it matches.

The wedge is not "call a video model" — anyone can do that. It is the **production
orchestration around the models**: reusable character assets, multi-engine routing,
a script→storyboard→shots→assembly→review pipeline, and a self-correcting quality
loop, all observable and cost-traced. That orchestration layer is what we already
spent the first half building.

---

## 2. Where we are — the built half (Phase 0, done)

The foundation is the genuinely hard infrastructure, and it exists and is tested
(v1.10.0, 169 tests, green CI). These primitives carry directly into v2:

| Built primitive | Reused for v2 as |
| --- | --- |
| Async LangGraph pipeline (script→tts→avatar→store→notify) | The film pipeline spine; nodes are added, not replaced |
| Engine registry (3 avatar engines behind one contract) | Scene-engine registry routing on style / cost / content-policy |
| Multi-provider fallback + circuit breakers | Same resilience across new providers (Sora, Kling, ElevenLabs) |
| Celery + Redis async jobs, SSE, DLQ | Long multi-scene renders; per-scene fan-out |
| Per-job trace (job_id correlation across audit tables) | Per-scene trace; the quality-loop iteration history |
| Two eval suites (script + planner-agent) | Extended to score rendered video (the quality loop) |
| Conversational planner + per-user memory | The director conversation; remembers a user's style |
| Operator console (Studio/Library/Dashboard/Monitoring/Architecture/Assistant) | Add a film Studio + Characters gallery; reuse the shell |
| asyncpg/loop, Celery time-limit, replay fixes | Reliability under minutes-long film renders (already paid for) |

**What this means:** v2 is additive. We add a Character asset, scene engines,
a storyboard/composition layer, finishing nodes, and a quality loop — on top of a
pipeline that already orchestrates, falls back, traces, evaluates, and remembers.

---

## 3. The production methodology (industry-standard, mapped to agents)

Real AI film production is not "prompt → video." It is a pipeline. Each stage maps
to a node in our existing graph:

1. **Director agent** — brief → screenplay → **storyboard** (ordered scenes; each
   scene carries shot description, camera, dialogue, mood, style). Azure OpenAI.
2. **Character asset** — ingest photo/video/live → sample reference frames →
   optional per-person style LoRA → optional cloned voice. Created once, reused.
3. **Shot generation (fan-out)** — per scene, an identity-locked clip in the
   chosen style, via the routed scene engine.
4. **Dialogue + lip-sync** — voice (Azure / ElevenLabs) → lip-sync the character.
5. **Score** — mood-matched music per the storyboard.
6. **Assembly** — stitch shots, transitions, captions, color, output formats.
7. **Quality loop (the centrepiece)** — a vision judge scores each shot against its
   storyboard cell; failing shots are re-rendered (targeted, not full regen) under
   iteration + cost caps, until they match the brief.

---

## 4. Architecture (fused, end to end)

```
Brief / conversation
       │
       ▼
 Director agent (Azure OpenAI) ──► Storyboard (scenes[])
       │                                  │
 Character asset ◄── ingest (FFmpeg)      │  fan-out per scene
   refs + style LoRA + voice              ▼
       │                          Scene engine (routed)
       │                          ├─ Azure Sora 2     (stylized, audio, Remix)
       │                          ├─ Kling 3.0 / fal  (photoreal real-person, Char-ID)
       │                          └─ FLUX-LoRA still → image-to-video (styles)
       ▼                                  │
   Voice (Azure / ElevenLabs) ──► Lip-sync (VEED Fabric / fal)
       │                                  │
   Music score (ElevenLabs / AIVA)        ▼
       │                          Assembly (FFmpeg: stitch, captions, color)
       └──────────────┬───────────────────┘
                       ▼
            Quality loop  ── vision judge vs storyboard ──► re-render failing shots
                       │        (Sora Remix / re-prompt; caps on iterations + cost)
                       ▼
                 Finished short  ──► Library + per-scene trace + cost breakdown
```

**Engine routing is the sophisticated part.** The scene engine is chosen on three
axes, not one:
- **Style** — realistic vs anime/Pixar/3D.
- **Cost** — draft tier for iteration, hero tier for finals.
- **Content policy** — Azure Sora 2 blocks photorealistic real-person likeness, so
  those shots route to Kling/Seedance on fal (reference-image identity-lock); stylized
  shots stay on Azure. Routing by policy, not just price, is a real design point.

---

## 5. Verified technology stack + unit costs (June 2026)

| Step | Production choice | Verified unit cost | Platform |
| --- | --- | --- | --- |
| Director / planner / judge | Azure OpenAI (existing) | cents per call | **Azure** |
| Character ingest | FFmpeg frame-sampling (existing) | free | self |
| Style reference (anime/Pixar/realistic) | FLUX LoRA on fal | ~$2 / LoRA training run, then ~$0.035 / megapixel (~28 imgs/$1) | fal |
| **Scene video — primary** | **Azure Sora 2** (text/img/video→video, audio, Remix) | **$0.10 / second** | **Azure** |
| Scene video — alt / photoreal real-person | Kling 3.0 via fal (Character-ID) | $0.084/s (Std), $0.112/s (Pro), $0.168/s (audio) | fal |
| Scene video — budget draft | Wan 2.6 / Seedance fast | ~$0.05–0.15 / second | fal |
| Voice (standard) | Azure Speech (existing) | cents | **Azure** |
| Voice (cloned / dubbing) | ElevenLabs | ~$0.08–0.17 / 1k chars; Starter $5/mo | ElevenLabs |
| Lip-sync | VEED Fabric / Lipsync on fal | $0.08/s (480p), $0.15/s (720p); or $0.40/min | fal |
| Music score | ElevenLabs Music ($9.99) / Suno / AIVA (cinematic) | $10–30/mo subscription | API |
| Assembly / captions / color | FFmpeg (existing); Shotstack optional | free; Shotstack ~$0.20–0.30 / rendered min | self / API |
| Quality judge (vision) | Azure OpenAI vision | cents per call | **Azure** |

**Key fact:** scene generation, scripting, voice, and the quality judge all run on
**Azure** (Sora 2 is in Azure AI Foundry at $0.10/sec). fal is the secondary engine
for stylization, lip-sync, and the photoreal/real-person route Azure's Responsible
AI blocks. We already integrate the fal pattern (`FalAvatarClient`) and the Azure
pattern (LLM/TTS), so both fit the existing registry.

---

## 6. Roadmap — from here to done

Each phase ships as a tagged release with tests and green CI, same cadence as v1.x.

### Phase 1 — Character asset + Azure Sora 2 scene engine  (v2.0.0)
- `Character` model + tables (migration 0007): reference frames, style, voice id.
- Ingest endpoint: photo → frames; video/live → FFmpeg best-frame sampling.
- `Sora2Client` added to the scene-engine registry beside fal; verify the current
  Azure AI Foundry Sora 2 request schema against Microsoft Learn before coding.
- Reuse storage, validation, tracing, tests. Console: a **Characters** gallery.
- *Exit:* ingest a person, generate one Sora 2 scene from a reference, traced.

### Phase 2 — Style engines + voice + lip-sync  (v2.1.0)
- `StyleEngine` registry (realistic / anime / Pixar-3D / extensible) behind one
  contract — mirrors the avatar-engine pattern. FLUX-LoRA image-to-image; optional
  per-character trained LoRA for stronger likeness.
- ElevenLabs voice provider behind the existing TTS fallback (cloned voices).
- VEED Fabric lip-sync node so the character speaks the dialogue.
- *Exit:* same person rendered in 3 styles, speaking, lip-synced.

### Phase 3 — Director agent + multi-scene composition  (v2.2.0)
- Extend the planner: brief → `Storyboard` (scenes[] with shot/camera/dialogue/style).
- Pipeline fan-out: per-scene generation → FFmpeg stitch + transitions + captions.
- Music score node, mood-matched to the storyboard.
- Per-scene tracing in the existing trace view.
- *Exit:* a 30–60s multi-scene short from one brief, assembled and scored.

### Phase 4 — The self-correcting quality loop  (v2.3.0) — the centrepiece
- Vision-judge node: score each rendered shot against its storyboard cell.
- Re-render path: below threshold → re-prompt / Sora 2 Remix that shot only.
- Bounded by max-iterations + max-cost caps (a runaway loop cannot drain credits);
  every iteration traced and costed.
- Extends the eval harness from scoring scripts to scoring rendered video.
- *Exit:* a shot that fails the brief is detected and improved automatically, with
  the iteration history visible in the trace.

### Phase 5 — Film Studio console + deployment  (v2.4.0)
- **Studio (film)** view: character → style → brief → watch storyboard render →
  see the quality loop iterate live. Reuse the console shell.
- Public deployment (Azure Container Apps) — a clickable URL; the biggest single
  multiplier for the whole project.
- *Exit:* a stranger can open a URL, create a short, and watch it self-correct.

### Phase 6 — Hardening + finishing  (v2.5.0)
- Auth/API-key layer (the standing gap), idempotency keys, outbound webhooks.
- Upscale/finish pass for hero renders; p50/p95/p99 latency in Monitoring.
- Cost dashboard per character/per project; budget guardrails surfaced in UI.

---

## 7. Budget

**Azure credits (the ~20-day window):** cover scripting, voice, the vision judge,
**and** Sora 2 scene generation. A 30-second cinematic short ≈ 6 shots × 5s = 30s of
Sora 2 at $0.10/s ≈ **~$3 of video**, plus cents of LLM/voice. Dozens of these fit
inside the free credits — production is largely **$0 out-of-pocket** during the window.

**fal top-up (the only real spend):** stylization LoRAs (~$2 each), lip-sync
($0.08–0.15/s), and Kling for the photoreal/real-person shots Azure blocks.
**$30–50 covers the entire build** with room for LoRA experiments and many
quality-loop re-renders.

**Optional subscriptions:** ElevenLabs Starter ($5/mo) for cloned voices/dubbing;
ElevenLabs Music ($9.99) or AIVA for scores; Shotstack only if you prefer managed
assembly over FFmpeg.

**Per finished cinematic short in production: ~$3–6** (Azure Sora video + cents of
LLM/voice + a couple of fal lip-sync/restyle calls + the loop's 1–2 re-renders).

**Total to ship v2: ~$30–50 on fal + existing Azure credits.** Not hundreds.

---

## 8. Scope, constraints, and honest risks

- **Achievable target:** broadcast-quality **15–60s cinematic shorts / reels** with
  identity-locked stylized characters, real voice + lip-sync, a score, captioned
  assembly, and an agentic quality loop. A serious portfolio platform and product wedge.
- **Not in scope for v2:** 10-minute studio-VFX films one-shot. Runtime scales cost
  linearly and character consistency degrades past a few minutes — that's a frontier
  problem, not a 20-day build.
- **Azure Sora content policy:** blocks photorealistic real-person likeness; those
  shots route to Kling/Seedance on fal. This is *why* multi-engine routing exists.
- **Character consistency:** production-ready in 2026 (Kling Character-ID ~90%+ across
  shots with good references) but not perfect; the quality loop is the mitigation.
- **Cost runaway:** the quality loop must have hard iteration + spend caps from day one.
- **Preview APIs:** Sora 2 on Azure is in preview; verify the schema before each use
  and keep the engine pluggable so a schema change is a one-file fix.

---

## 9. Definition of done (v2)

1. Ingest a person (photo/video/live) → a reusable character asset.
2. Choose a style (realistic / anime / Pixar-3D) and describe a short.
3. The director agent produces a storyboard; scenes render with the locked character.
4. Dialogue is voiced and lip-synced; a score and captions are added; shots assembled.
5. The quality loop checks each shot against the brief and re-renders until it matches.
6. The whole run is traced and cost-attributed; the finished short is in the Library.
7. It runs at a public URL; CI is green; tests cover the new services and the loop.

---

*Sources for cost figures (verified June 2026): Azure AI Foundry / Microsoft Learn
(Sora 2 $0.10/sec, preview, RAI photorealistic block); fal.ai model pages (Kling 3.0,
FLUX-LoRA training + image-to-image, VEED Fabric/Lipsync); ElevenLabs pricing pages;
industry pricing comparisons (Kling/Seedance/Wan per-second rates).*
