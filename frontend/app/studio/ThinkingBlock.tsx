"use client";

import { useEffect, useRef, useState } from "react";
import type { StageEvent } from "@/lib/api";

// A Claude-style thinking block: streams stage lines live while the turn runs,
// pulses on the active line, and auto-collapses to a one-line summary when done.
// Click the header to expand/collapse.

export type ThinkingState = {
  events: StageEvent[];
  active: boolean; // still streaming
};

const WORK_STAGES = new Set(["interpreting", "storyboarding", "rendering", "thinking"]);

export function ThinkingBlock({ state }: { state: ThinkingState }) {
  const { events, active } = state;
  // collapsed by default (like Claude) — the header's live pulse shows it's working;
  // expand to read the trace. We never auto-open; the user is in control.
  const [open, setOpen] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [events, open]);

  const lines = events.filter((e) => !["interpreted", "done", "failed", "end"].includes(e.stage));
  const summary = active
    ? "Thinking…"
    : `Thought through ${lines.length} step${lines.length === 1 ? "" : "s"}`;

  return (
    <div className={`think ${active ? "live" : ""}`}>
      <button
        className="thead"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className={`spark ${active ? "on" : ""}`} aria-hidden />
        <span className="summary">{summary}</span>
        <span className="chev">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="tbody" ref={bodyRef}>
          {lines.map((e, i) => {
            const isLast = i === lines.length - 1;
            const working = active && isLast && WORK_STAGES.has(e.stage);
            return (
              <div key={i} className={`tline ${working ? "working" : ""}`}>
                <span className="tdot" aria-hidden />
                <span className="ttext">{e.message}</span>
              </div>
            );
          })}
        </div>
      )}

      <style jsx>{`
        .think {
          border: 1px solid var(--border);
          border-radius: 10px;
          background: rgba(29, 35, 44, 0.4);
          overflow: hidden;
        }
        .think.live {
          border-color: var(--amber-dim);
        }
        .thead {
          width: 100%;
          display: flex;
          align-items: center;
          gap: 9px;
          background: none;
          border: none;
          padding: 10px 13px;
          color: var(--muted);
          font-size: 13px;
          text-align: left;
        }
        .thead:hover {
          color: var(--text);
        }
        .spark {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: var(--faint);
          flex: none;
        }
        .spark.on {
          background: var(--amber);
          animation: spark 1.1s ease-in-out infinite;
        }
        @keyframes spark {
          0%,
          100% {
            opacity: 0.4;
            box-shadow: 0 0 0 0 rgba(242, 181, 88, 0.4);
          }
          50% {
            opacity: 1;
            box-shadow: 0 0 0 5px rgba(242, 181, 88, 0);
          }
        }
        .summary {
          flex: 1;
          font-family: var(--mono);
          font-size: 12px;
          letter-spacing: 0.02em;
        }
        .chev {
          color: var(--faint);
          font-size: 11px;
        }
        .tbody {
          max-height: 260px;
          overflow-y: auto;
          padding: 4px 13px 12px 13px;
          border-top: 1px solid var(--border);
        }
        .tline {
          display: flex;
          gap: 10px;
          padding: 5px 0;
          align-items: flex-start;
          animation: rise 0.25s ease;
        }
        @keyframes rise {
          from {
            opacity: 0;
            transform: translateY(3px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .tdot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: var(--faint);
          margin-top: 7px;
          flex: none;
        }
        .tline.working .tdot {
          background: var(--amber);
          animation: spark 1.1s ease-in-out infinite;
        }
        .ttext {
          font-size: 13px;
          line-height: 1.5;
          color: var(--muted);
        }
        .tline.working .ttext {
          color: var(--text);
        }
      `}</style>
    </div>
  );
}
