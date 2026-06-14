"use client";

import type { StageEvent } from "@/lib/api";

// The signature element: each AI stage lands as a typed entry on a vertical
// timeline, so you watch the film take shape rather than waiting on a spinner.

const STAGE_META: Record<string, { label: string; tone: string }> = {
  interpreting: { label: "Interpreting", tone: "work" },
  interpreted: { label: "Interpretation", tone: "read" },
  storyboarding: { label: "Storyboarding", tone: "work" },
  storyboarded: { label: "Storyboard", tone: "read" },
  rendering: { label: "Rendering", tone: "work" },
  thinking: { label: "Thinking", tone: "work" },
  clarify: { label: "Needs you", tone: "read" },
  done: { label: "Done", tone: "done" },
  failed: { label: "Failed", tone: "fail" },
};

export type FeedItem = StageEvent & { id: number; active?: boolean };

export function StageFeed({ items }: { items: FeedItem[] }) {
  return (
    <ol className="feed">
      {items.map((it) => {
        const meta = STAGE_META[it.stage] ?? { label: it.stage, tone: "work" };
        const isInterp = it.stage === "interpreted";
        return (
          <li key={it.id} className={`feeditem tone-${meta.tone} ${it.active ? "active" : ""}`}>
            <span className="dot" aria-hidden />
            <div className="body">
              <span className="stage">{meta.label}</span>
              {isInterp ? (
                <Interpretation text={it.message} />
              ) : (
                <p className="msg">{it.message}</p>
              )}
            </div>
          </li>
        );
      })}
      <style jsx>{`
        .feed {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 2px;
          position: relative;
        }
        .feeditem {
          display: grid;
          grid-template-columns: 22px 1fr;
          gap: 12px;
          padding: 10px 0;
          position: relative;
        }
        .feeditem:not(:last-child)::before {
          content: "";
          position: absolute;
          left: 10px;
          top: 22px;
          bottom: -2px;
          width: 1px;
          background: var(--border);
        }
        .dot {
          width: 9px;
          height: 9px;
          margin: 5px auto 0;
          border-radius: 50%;
          background: var(--faint);
          box-shadow: 0 0 0 3px var(--base);
        }
        .tone-work .dot {
          background: var(--amber);
        }
        .tone-work.active .dot {
          animation: pulse 1.2s ease-in-out infinite;
        }
        .tone-read .dot {
          background: var(--muted);
        }
        .tone-done .dot {
          background: var(--cyan);
        }
        .tone-fail .dot {
          background: var(--rose);
        }
        @keyframes pulse {
          0%,
          100% {
            box-shadow: 0 0 0 3px var(--base), 0 0 0 5px rgba(242, 181, 88, 0.25);
          }
          50% {
            box-shadow: 0 0 0 3px var(--base), 0 0 0 9px rgba(242, 181, 88, 0);
          }
        }
        .stage {
          font-family: var(--mono);
          font-size: 10.5px;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: var(--muted);
          display: block;
          margin-bottom: 2px;
        }
        .tone-done .stage {
          color: var(--cyan);
        }
        .tone-fail .stage {
          color: var(--rose);
        }
        .msg {
          font-size: 14px;
          color: var(--text);
        }
      `}</style>
    </ol>
  );
}

// The interpretation arrives as markdown-ish text (a **title**, a premise, a
// numbered beat list). Render it as a distinct card — it's the moment the app
// shows the user how it understood them, before spending a render.
function Interpretation({ text }: { text: string }) {
  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  return (
    <div className="interp">
      {lines.map((line, i) => {
        const bold = line.match(/\*\*(.+?)\*\*/);
        if (bold) {
          return (
            <p key={i} className="interp-title">
              {line.replace(/\*\*/g, "")}
            </p>
          );
        }
        if (/^\s*\d+\./.test(line)) {
          return (
            <p key={i} className="interp-beat">
              {line.trim()}
            </p>
          );
        }
        return (
          <p key={i} className="interp-line">
            {line}
          </p>
        );
      })}
      <style jsx>{`
        .interp {
          background: var(--surface-2);
          border: 1px solid var(--border);
          border-left: 2px solid var(--amber);
          border-radius: 8px;
          padding: 14px 16px;
          margin-top: 4px;
        }
        .interp-title {
          font-size: 15px;
          font-weight: 600;
          color: var(--text);
          margin-bottom: 6px;
        }
        .interp-line {
          font-size: 13.5px;
          color: var(--muted);
          margin: 4px 0;
        }
        .interp-beat {
          font-size: 13px;
          color: var(--text);
          font-family: var(--mono);
          margin: 2px 0;
          padding-left: 4px;
        }
      `}</style>
    </div>
  );
}
