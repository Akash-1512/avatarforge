"use client";

import { useEffect, useRef, useState } from "react";
import {
  auth,
  createFilm,
  editFilm,
  listCharacters,
  listFilms,
  mediaUrl,
  streamFilm,
  type CastMember,
  type Character,
  type FilmSummary,
  type StageEvent,
} from "@/lib/api";
import { ThinkingBlock, type ThinkingState } from "./ThinkingBlock";

// A turn in the conversation. A user turn is a plain message. An assistant turn
// carries a streaming thinking trace, then a reply + (optionally) a video.
type Turn =
  | { kind: "user"; id: number; text: string }
  | {
      kind: "assistant";
      id: number;
      thinking: ThinkingState;
      reply: string;
      clipId: string | null;
      interpretation: string | null;
    };

const THEMES = ["cinematic", "anime", "pixar", "3d", "claymation", "watercolor", "realistic"];

export default function StudioPage() {
  const [authed, setAuthed] = useState(false);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [films, setFilms] = useState<FilmSummary[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  // composer state
  const [text, setText] = useState("");
  const [theme, setTheme] = useState("cinematic");
  const [cast, setCast] = useState<CastMember[]>([]);
  const [error, setError] = useState<string | null>(null);

  const counter = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const started = sessionId !== null;

  useEffect(() => {
    setAuthed(!!auth.token);
    if (auth.token) {
      listCharacters().then(setCharacters).catch(() => setCharacters([]));
      listFilms().then(setFilms).catch(() => setFilms([]));
    }
  }, []);

  const refreshFilms = () => listFilms().then(setFilms).catch(() => {});

  // keep the conversation pinned to the live edge as content streams
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const nextId = () => (counter.current += 1);

  // route a stage event into the most recent assistant turn
  const onEvent = (assistantId: number) => (e: StageEvent) => {
    setTurns((prev) =>
      prev.map((t) => {
        if (t.kind !== "assistant" || t.id !== assistantId) return t;
        const events = [...t.thinking.events, e];
        let reply = t.reply;
        let clipId = t.clipId;
        let interpretation = t.interpretation;
        if (e.stage === "interpreted") {
          interpretation = e.message;
        }
        if (e.stage === "done") {
          reply = e.message;
          if (e.data?.clip_id) clipId = String(e.data.clip_id);
        }
        if (e.stage === "failed") reply = e.message;
        if (e.stage === "clarify") reply = e.message;
        return { ...t, thinking: { events, active: t.thinking.active }, reply, clipId, interpretation };
      }),
    );
  };

  const finish = (assistantId: number) => () => {
    setTurns((prev) =>
      prev.map((t) =>
        t.kind === "assistant" && t.id === assistantId
          ? { ...t, thinking: { ...t.thinking, active: false } }
          : t,
      ),
    );
    setRunning(false);
    refreshFilms();
  };

  const send = async () => {
    const msg = text.trim();
    if (msg.length === 0 || running) return;

    if (!started) {
      // first message: create the film from script + cast + theme
      if (cast.length === 0) {
        setError("Add at least one avatar to the cast.");
        return;
      }
      setError(null);
      const userId = nextId();
      const aId = nextId();
      setTurns([
        { kind: "user", id: userId, text: msg },
        { kind: "assistant", id: aId, thinking: { events: [], active: true }, reply: "", clipId: null, interpretation: null },
      ]);
      setText("");
      setRunning(true);
      try {
        const { session_id } = await createFilm(msg, cast, theme);
        setSessionId(session_id);
        streamFilm(session_id, onEvent(aId), finish(aId));
      } catch (e) {
        onEvent(aId)({ stage: "failed", message: e instanceof Error ? e.message : "Could not start" });
        finish(aId)();
      }
      return;
    }

    // subsequent messages: edits on the existing session
    const userId = nextId();
    const aId = nextId();
    setTurns((prev) => [
      ...prev,
      { kind: "user", id: userId, text: msg },
      { kind: "assistant", id: aId, thinking: { events: [], active: true }, reply: "", clipId: null, interpretation: null },
    ]);
    setText("");
    setRunning(true);
    editFilm(sessionId!, msg, onEvent(aId), finish(aId));
  };

  const toggleCast = (c: Character) => {
    setCast((prev) =>
      prev.some((m) => m.avatar_id === c.id)
        ? prev.filter((m) => m.avatar_id !== c.id)
        : [
            ...prev,
            {
              role: c.name.toUpperCase().replace(/\s+/g, "_"),
              avatar_id: c.id,
              voice: "",
              style: c.default_style,
              is_real_person: c.is_real_person,
            },
          ],
    );
  };

  if (!authed) {
    return (
      <main className="gate">
        <p className="eyebrow">contentforge studio</p>
        <h1>Sign in to direct.</h1>
        <a className="btn primary" href="/login">Go to sign in</a>
        <style jsx>{`
          .gate { min-height: 100vh; display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 14px; text-align: center; }
          h1 { font-size: 28px; font-weight: 700; }
          .btn { margin-top: 8px; }
        `}</style>
      </main>
    );
  }

  return (
    <div className="layout">
      <aside className="rail">
        <p className="raillabel">Your films</p>
        {films.length === 0 ? (
          <p className="railempty">Nothing yet. Make your first below.</p>
        ) : (
          <ul className="filmlist">
            {films.map((f) => (
              <li key={f.id} className={`filmrow ${f.id === sessionId ? "current" : ""}`}>
                <span className="ftitle">{f.title || "Untitled"}</span>
                <span className="fmeta">
                  {f.theme || "—"} · {f.scene_count} scene{f.scene_count === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ul>
        )}
        <a className="newfilm" href="/studio" onClick={(e) => { e.preventDefault(); window.location.reload(); }}>
          + New film
        </a>
      </aside>

      <main className="shell">
      <header className="top">
        <div>
          <p className="eyebrow">contentforge</p>
          <h1>Studio</h1>
        </div>
        <nav>
          <a href="/avatars">Avatars</a>
          <a href="/login" onClick={() => auth.clear()}>Sign out</a>
        </nav>
      </header>

      <div className="convo" ref={scrollRef}>
        {turns.length === 0 ? (
          <div className="empty">
            <p className="eyebrow">direct in conversation</p>
            <h2>Write a scene. Watch it think.</h2>
            <p className="lead">
              Describe the film and name your characters. The studio interprets it,
              storyboards the shots, renders each scene, and shows you the cut — then you
              keep directing by chat.
            </p>
          </div>
        ) : (
          turns.map((t) =>
            t.kind === "user" ? (
              <div key={t.id} className="turn user">
                <div className="bubble">{t.text}</div>
              </div>
            ) : (
              <div key={t.id} className="turn assistant">
                {t.thinking.events.length > 0 && <ThinkingBlock state={t.thinking} />}
                {t.interpretation && <Interp text={t.interpretation} />}
                {t.reply && <div className="reply">{t.reply}</div>}
                {t.clipId && (
                  <video className="vid" controls src={mediaUrl(t.clipId)} key={t.clipId} />
                )}
              </div>
            ),
          )
        )}
      </div>

      <div className="composer">
        {!started && (
          <div className="setup">
            <div className="chips">
              {characters.length === 0 ? (
                <span className="nochars">
                  No avatars yet — <a href="/avatars">create one</a> to add a cast.
                </span>
              ) : (
                characters.map((c) => (
                  <button
                    key={c.id}
                    className={`chip ${cast.some((m) => m.avatar_id === c.id) ? "on" : ""}`}
                    onClick={() => toggleCast(c)}
                  >
                    {c.name}
                    <span className="cs">{c.default_style}</span>
                  </button>
                ))
              )}
            </div>
            <select className="theme" value={theme} onChange={(e) => setTheme(e.target.value)}>
              {THEMES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        )}
        <div className="inputrow">
          <textarea
            className="composer-input"
            placeholder={
              started
                ? "Keep directing — “make it brighter”, “give KAI a deeper voice”, “make it anime”"
                : "Describe the film. Name your characters — e.g. ARIA welcomes the viewer, then KAI explains the product."
            }
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={started ? 1 : 3}
          />
          <button
            className="btn primary send"
            onClick={send}
            disabled={running || text.trim().length === 0 || (!started && cast.length === 0)}
          >
            {running ? "…" : started ? "Send" : "Make film"}
          </button>
        </div>
        {error && <p className="cerr">{error}</p>}
      </div>

      <style jsx>{`
        .layout {
          display: grid;
          grid-template-columns: 240px 1fr;
          height: 100vh;
        }
        @media (max-width: 760px) {
          .layout {
            grid-template-columns: 1fr;
          }
          .rail {
            display: none;
          }
        }
        .rail {
          border-right: 1px solid var(--border);
          padding: 22px 16px;
          display: flex;
          flex-direction: column;
          overflow-y: auto;
        }
        .raillabel {
          font-family: var(--mono);
          font-size: 10.5px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--faint);
          margin-bottom: 14px;
        }
        .railempty {
          font-size: 12.5px;
          color: var(--faint);
        }
        .filmlist {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 4px;
          flex: 1;
        }
        .filmrow {
          padding: 9px 10px;
          border-radius: 8px;
          cursor: default;
          border: 1px solid transparent;
        }
        .filmrow.current {
          background: var(--surface);
          border-color: var(--border);
        }
        .ftitle {
          display: block;
          font-size: 13px;
          color: var(--text);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .fmeta {
          font-family: var(--mono);
          font-size: 10px;
          color: var(--faint);
        }
        .newfilm {
          margin-top: 14px;
          font-size: 13px;
          color: var(--amber);
          padding: 8px 10px;
        }
        .newfilm:hover {
          color: #f6c272;
        }
        .shell {
          max-width: 820px;
          margin: 0 auto;
          width: 100%;
          height: 100vh;
          display: flex;
          flex-direction: column;
          padding: 0 20px;
        }
        .top {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          padding: 22px 0 16px;
          border-bottom: 1px solid var(--border);
        }
        h1 { font-size: 22px; font-weight: 700; }
        nav { display: flex; gap: 18px; }
        nav a { font-size: 13px; color: var(--muted); }
        nav a:hover { color: var(--amber); }
        .convo {
          flex: 1;
          overflow-y: auto;
          padding: 24px 0;
          display: flex;
          flex-direction: column;
          gap: 18px;
        }
        .empty {
          margin: auto;
          text-align: center;
          max-width: 460px;
        }
        .empty h2 { font-size: 26px; font-weight: 700; margin: 10px 0 12px; letter-spacing: -0.01em; }
        .lead { color: var(--muted); font-size: 14px; line-height: 1.6; }
        .turn { display: flex; flex-direction: column; }
        .turn.user { align-items: flex-end; }
        .bubble {
          background: var(--amber);
          color: #1a1205;
          padding: 10px 14px;
          border-radius: 14px 14px 4px 14px;
          font-size: 14px;
          max-width: 80%;
          white-space: pre-wrap;
        }
        .turn.assistant { gap: 10px; }
        .reply { font-size: 15px; line-height: 1.6; color: var(--text); }
        .vid { width: 100%; border-radius: 12px; border: 1px solid var(--border); }
        .composer {
          border-top: 1px solid var(--border);
          padding: 14px 0 20px;
        }
        .setup { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
        .chips { display: flex; flex-wrap: wrap; gap: 7px; flex: 1; }
        .nochars { font-size: 13px; color: var(--muted); }
        .nochars a { color: var(--amber); }
        .chip {
          background: var(--surface-2);
          border: 1px solid var(--border);
          border-radius: 999px;
          padding: 5px 11px;
          color: var(--text);
          font-size: 12.5px;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .chip.on { border-color: var(--amber); color: var(--amber); }
        .cs { font-family: var(--mono); font-size: 9.5px; color: var(--faint); }
        .theme {
          background: var(--surface-2);
          border: 1px solid var(--border);
          color: var(--text);
          border-radius: 8px;
          padding: 7px 10px;
          font-size: 13px;
        }
        .inputrow { display: flex; gap: 10px; align-items: flex-end; }
        .composer-input {
          flex: 1;
          background: var(--surface);
          border: 1px solid var(--border);
          color: var(--text);
          border-radius: 12px;
          padding: 12px 14px;
          font-size: 14px;
          line-height: 1.5;
          resize: none;
        }
        .composer-input:focus { outline: none; border-color: var(--amber-dim); }
        .send { white-space: nowrap; height: 44px; }
        .cerr { color: var(--rose); font-size: 13px; margin-top: 8px; }
      `}</style>
    </main>
    </div>
  );
}

// The interpretation as a distinct card inside the assistant turn.
function Interp({ text }: { text: string }) {
  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  return (
    <div className="interp">
      {lines.map((line, i) => {
        if (/\*\*(.+?)\*\*/.test(line))
          return <p key={i} className="it">{line.replace(/\*\*/g, "")}</p>;
        if (/^\s*\d+\./.test(line)) return <p key={i} className="ib">{line.trim()}</p>;
        return <p key={i} className="il">{line}</p>;
      })}
      <style jsx>{`
        .interp {
          background: var(--surface-2);
          border: 1px solid var(--border);
          border-left: 2px solid var(--amber);
          border-radius: 10px;
          padding: 14px 16px;
        }
        .it { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
        .il { font-size: 13.5px; color: var(--muted); margin: 4px 0; }
        .ib { font-size: 13px; color: var(--text); font-family: var(--mono); margin: 2px 0; }
      `}</style>
    </div>
  );
}
