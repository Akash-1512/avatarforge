# contentforge — web studio

The chat-native frontend for contentforge: sign in, create avatars, and **direct
films in conversation** — watch the AI interpret your script, storyboard, render each
scene, and assemble the cut live, then keep editing by chat.

## Run it

The backend (FastAPI) must be running on `http://localhost:8000` first
(`.\make.ps1 dev` in the repo root).

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

Calls to `/api/*` are proxied to the backend (see `next.config.mjs`), so the browser
sees same-origin and there's no CORS to configure. To point at a different backend,
set `NEXT_PUBLIC_API_BASE`.

## What's here

- `/login` — register or sign in (email + password → JWT, stored client-side).
- `/avatars` — create avatars (name, look, real-or-stylized, photo) and list them.
- `/studio` — **the centerpiece.** Write a script, pick a theme, add cast from your
  avatars, and hit *Make the film*. The right panel streams the AI's thinking as a
  director's timeline (interpret → storyboard → render → done), shows the video, and
  lets you refine it with chat ("make it brighter", "give KAI a deeper voice").

## How the live feed works

The studio consumes the backend's SSE stage stream
(`GET /studio/film/{id}/stream`) and edit stream (`POST /studio/film/{id}/edit`).
Because `EventSource` is GET-only and can't set headers, the JWT rides as a `?token=`
query param, and the POST edit stream is read via a `fetch` body reader. See
`lib/api.ts`.

## Build

```bash
npm run build && npm start
```
