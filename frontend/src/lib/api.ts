// Typed client for the contentforge API. In dev, Vite proxies /api to :8000;
// in production set VITE_API_BASE to the deployed API origin.
const BASE = (import.meta.env.VITE_API_BASE ?? "") + "/api/v1";

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, opts);
  const text = await res.text();
  const body = text ? JSON.parse(text) : {};
  if (!res.ok) {
    throw new Error(body?.detail ? JSON.stringify(body.detail) : `${res.status}`);
  }
  return body as T;
}

function json(path: string, method: string, payload: unknown) {
  return { path, method, payload };
}

// ---- types mirror the API responses ----
export interface SceneEngines {
  engines: string[];
  default: string;
  real_face_capable: string[];
}
export interface Character {
  id: string;
  name: string;
  source_kind: string;
  default_style: string;
  is_real_person: boolean;
  frame_count: number;
  status: string;
  created_at: string | null;
}
export interface Scene {
  shot: string;
  camera: string;
  dialogue: string;
  seconds: number;
}
export interface Storyboard {
  title: string;
  style: string;
  scenes: Scene[];
}
export interface Attempt {
  iteration: number;
  engine: string;
  score: number;
  issues: string[];
  est_cost_usd: number;
}
export interface RefineResult {
  clip_id: string;
  passed: boolean;
  best_score: number;
  iterations: number;
  est_cost_usd: number;
  attempts: Attempt[];
}

export const api = {
  mediaUrl: (id: string) => `${BASE}/media/${id}`,

  health: () => req<{ status: string; version: string }>("/health"),
  sceneEngines: () => req<SceneEngines>("/scene/engines"),
  sceneStyles: () => req<{ styles: string[]; configured: boolean }>("/scene/styles"),

  listCharacters: (userId: string) =>
    req<{ characters: Character[] }>(`/characters/${userId}`),
  deleteCharacter: (userId: string, id: string) =>
    req(`/characters/${userId}/${id}`, { method: "DELETE" }),
  createCharacter: (form: FormData) =>
    req<Character>("/characters", { method: "POST", body: form }),
  restyle: (userId: string, id: string, style: string) => {
    const f = new FormData();
    f.append("style", style);
    return req<{ still_id: string; style: string }>(
      `/characters/${userId}/${id}/restyle`,
      { method: "POST", body: f }
    );
  },

  storyboard: (brief: string, style?: string) =>
    req<{ storyboard: Storyboard; scene_count: number; total_seconds: number }>(
      "/director/storyboard",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ brief, style }) }
    ),
  compose: (storyboard: Storyboard, characterId?: string | null) =>
    req<{ clip_id: string; scene_count: number; total_seconds: number }>("/film/compose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ storyboard, character_id: characterId ?? null }),
    }),
  refine: (
    prompt: string,
    opts: { seconds?: number; characterId?: string | null; threshold?: number; maxIterations?: number } = {}
  ) =>
    req<RefineResult>("/scene/refine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        seconds: opts.seconds ?? 4,
        character_id: opts.characterId ?? null,
        threshold: opts.threshold ?? 0.85,
        max_iterations: opts.maxIterations ?? 3,
      }),
    }),
};

// suppress unused-helper lint while keeping the json() shape documented
void json;
