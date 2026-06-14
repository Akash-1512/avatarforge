// Typed client for the contentforge backend. SSE streams must hit the backend
// directly (not the Next dev proxy, which buffers text/event-stream and delays
// every event until the stream closes). The backend allows localhost:3000 via CORS,
// so direct calls work. Override with NEXT_PUBLIC_API_BASE for other backends.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export function mediaUrl(clipId: string): string {
  return apiUrl(`/api/v1/media/${clipId}`);
}

export type AuthResult = {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  display_name: string;
};

export type Character = {
  id: string;
  name: string;
  default_style: string;
  is_real_person: boolean;
  frame_count: number;
};

export type CastMember = {
  role: string;
  avatar_id: string;
  voice: string;
  style: string;
  is_real_person: boolean;
};

export type StageEvent = {
  stage: string;
  message: string;
  data?: Record<string, unknown>;
};

const TOKEN_KEY = "cf_token";

export const auth = {
  get token(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
  },
  set(token: string) {
    window.localStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    window.localStorage.removeItem(TOKEN_KEY);
  },
};

function authHeaders(): HeadersInit {
  const t = auth.token;
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function register(
  email: string,
  password: string,
  displayName = "",
): Promise<AuthResult> {
  const res = await fetch(apiUrl("/api/v1/auth/register"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
  return jsonOrThrow<AuthResult>(res);
}

export async function login(email: string, password: string): Promise<AuthResult> {
  const res = await fetch(apiUrl("/api/v1/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return jsonOrThrow<AuthResult>(res);
}

export async function listCharacters(): Promise<Character[]> {
  const res = await fetch(apiUrl("/api/v1/characters"), { headers: authHeaders() });
  const body = await jsonOrThrow<{ characters: Character[] }>(res);
  return body.characters;
}

export async function createCharacter(form: FormData): Promise<Character> {
  const res = await fetch(apiUrl("/api/v1/characters"), {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return jsonOrThrow<Character>(res);
}

export type FilmSummary = {
  id: string;
  title: string;
  status: string;
  theme: string;
  clip_id: string | null;
  scene_count: number;
  updated_at: string | null;
};

export async function listFilms(): Promise<FilmSummary[]> {
  const res = await fetch(apiUrl("/api/v1/studio/films"), { headers: authHeaders() });
  const body = await jsonOrThrow<{ films: FilmSummary[] }>(res);
  return body.films;
}

export async function createFilm(
  script: string,
  cast: CastMember[],
  theme: string,
): Promise<{ session_id: string; status: string }> {
  const res = await fetch(apiUrl("/api/v1/studio/film"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ script, cast, theme }),
  });
  return jsonOrThrow<{ session_id: string; status: string }>(res);
}

// Stream a stage feed (produce or edit) over SSE. EventSource can't set headers,
// so the JWT rides as a query param — exactly what the backend expects.
export function streamFilm(
  sessionId: string,
  onEvent: (e: StageEvent) => void,
  onDone: () => void,
): () => void {
  const token = auth.token ?? "";
  const url = apiUrl(`/api/v1/studio/film/${sessionId}/stream?token=${encodeURIComponent(token)}`);
  return consume(url, onEvent, onDone);
}

export function editFilm(
  sessionId: string,
  message: string,
  onEvent: (e: StageEvent) => void,
  onDone: () => void,
): () => void {
  const token = auth.token ?? "";
  const url =
    apiUrl(`/api/v1/studio/film/${sessionId}/edit?token=${encodeURIComponent(token)}`) +
    `&message=${encodeURIComponent(message)}`;
  // edit is POST; EventSource only does GET, so we stream the POST body by hand.
  return consumePost(url, onEvent, onDone);
}

function consume(
  url: string,
  onEvent: (e: StageEvent) => void,
  onDone: () => void,
): () => void {
  const es = new EventSource(url);
  es.onmessage = (m) => {
    try {
      const ev = JSON.parse(m.data) as StageEvent;
      if (ev.stage === "end") {
        es.close();
        onDone();
        return;
      }
      onEvent(ev);
    } catch {
      /* ignore malformed frame */
    }
  };
  es.onerror = () => {
    es.close();
    onDone();
  };
  return () => es.close();
}

// POST SSE: fetch with a streamed body reader (EventSource is GET-only).
function consumePost(
  url: string,
  onEvent: (e: StageEvent) => void,
  onDone: () => void,
): () => void {
  const controller = new AbortController();
  (async () => {
    try {
      const res = await fetch(url, { method: "POST", signal: controller.signal });
      if (!res.body) {
        onDone();
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          try {
            const ev = JSON.parse(line.slice(6)) as StageEvent;
            if (ev.stage === "end") {
              onDone();
              return;
            }
            onEvent(ev);
          } catch {
            /* ignore */
          }
        }
      }
      onDone();
    } catch {
      onDone();
    }
  })();
  return () => controller.abort();
}
