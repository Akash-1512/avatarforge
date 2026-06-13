# avatarforge — demo playbook

Two demos that work together: a screen-capture that proves the product runs, and
a short clip the app renders of itself to use as the hook.

---

## 1. Screen-capture (the proof — README hero + LinkedIn)

Target: 35–50 seconds, no narration needed (text captions over it). The forge
pipeline lighting up *is* the story.

### Before recording
- Pick the **fal** engine for the on-camera run so a clip finishes in ~8 min,
  not ~25. Pre-run one job a few minutes earlier so the Dashboard has data.
- `docker compose up -d --force-recreate api worker`, wait ~8s, open
  `http://localhost:8000`.
- Browser at 1280×800, zoom 100%, hide bookmarks bar. Dark room for the dark UI.

### Shot list
1. **Open on the Studio** (2s). Top bar, "api live" green dot. Let it sit.
2. **Type the brief** (4s): `explain compound interest to teenagers, upbeat, 30s, in Hindi`.
   Type it live — motion reads as real.
3. **Preview plan** (4s): click it, let the plan card render — linger on the
   `rationale` line. This is the agent deciding, the most novel beat.
4. **Drop the photo** (2s): drag `face.jpg` in, preview appears.
5. **Forge video** (3s): click. Cut here — don't film the full render.
6. **Pipeline heating** (6s): show Script → Voice lighting up ember→green. If
   you used fal, you can show Avatar going active. Trim the dead wait in edit.
7. **Jump-cut to the finished video** (5s): the MP4 playing inline in the forge panel.
8. **Flip to Dashboard** (6s): spend tile (`$0.00xx`), fallback rate, success
   rates, jobs table with your run at the top.
9. **End on the pipeline or the dashboard** (2s), hold, fade.

### Capture
- Windows: **Win+Alt+R** (Xbox Game Bar) records the active window to MP4, or use
  ScreenToGif directly to GIF if you prefer no edit step.
- Edit out the render wait between shots 6 and 7 with a hard cut.

### Encode to a README GIF (ffmpeg, already on your machine)
```powershell
# from your recording demo.mp4 -> high-quality, small GIF via a palette
ffmpeg -i demo.mp4 -vf "fps=12,scale=900:-1:flags=lanczos,palettegen" -y palette.png
ffmpeg -i demo.mp4 -i palette.png -lavfi "fps=12,scale=900:-1:flags=lanczos[x];[x][1:v]paletteuse" -y docs/demo.gif
```
Keep it under ~8 MB so GitHub renders it inline. If it's bigger, drop fps to 10
or scale to 760.

### Put it in the README hero
```markdown
<p align="center"><img src="docs/demo.gif" alt="avatarforge — brief to talking-head video" width="900"></p>
```

---

## 2. avatarforge demoing itself (the hook)

Render this through your own Studio. Your face (or an original presenter photo),
your voice or a preset. It proves the product by *being* a product of it.

### Option A — one-take, ~30s (simplest)
Brief to paste into Studio → Quick:
```
A confident product engineer demoing a tool called avatarforge, upbeat but technical, 30 seconds
```
Then let the planner write it, or paste this script into Advanced as the topic
seed / use it verbatim if you wire a script override:

> This is avatarforge. You give it a photo and a line of text — it gives you a
> talking-head video. Behind that simple call is the part I actually built: a
> job queue, three rendering engines behind one interface, automatic fallback
> when a provider goes down, and a cost meter on every call. Same contract
> whether it runs on a free CPU model, a self-hosted GPU, or a managed API.
> Swap the engine, the rest doesn't move. That's the whole idea.

Tone notes for the render: keep it engineer-plain, no "unleash" or "seamless."
Short sentences. The line that lands is "swap the engine, the rest doesn't move."

### Option B — three short clips, different presenters/engines (shows range)
Render the same three lines on three engines/voices, cut together. This visibly
demonstrates the multi-engine thesis — each clip is a different engine doing the
identical job.

1. **sadtalker (free):** "I'm the cheap seat — a CPU model, no GPU bill. Good
   enough to prototype on, and it costs nothing to run."
2. **fal (managed):** "Need it sharp and fast? Same request, different engine. A
   managed API renders this one — about eight minutes, a buck forty."
3. **multi-language:** render line 1 again with `language: hi` — your face,
   Hindi voice. Caption: *same pipeline, any language.*

Cut them back to back with a title card between: "one contract · three engines ·
any language."

### The forge "power effects" (no copyrighted anything)
Use what's already yours: screen-record the **pipeline track heating up** from
the console and overlay it as a transition between spoken clips — the ember
glow and molten-conduit fill are your "power effect," on-brand and original.

---

## Posting order
1. Land the README GIF first (proof, on the repo).
2. LinkedIn post + the self-demo clip as the media (hook). Ask for the post copy
   when the clips are recorded.
