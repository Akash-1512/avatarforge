"use client";

import { useEffect, useRef, useState } from "react";
import { auth, createCharacter, listCharacters, type Character } from "@/lib/api";

const STYLES = ["realistic", "anime", "pixar", "3d", "claymation", "watercolor"];

export default function AvatarsPage() {
  const [chars, setChars] = useState<Character[]>([]);
  const [name, setName] = useState("");
  const [style, setStyle] = useState("realistic");
  const [real, setReal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (auth.token) listCharacters().then(setChars).catch(() => setChars([]));
  }, []);

  const create = async () => {
    const file = fileRef.current?.files?.[0];
    if (!name.trim() || !file) {
      setError("A name and a photo are required.");
      return;
    }
    setError(null);
    setBusy(true);
    const form = new FormData();
    form.append("name", name.trim());
    form.append("source_kind", "photo");
    form.append("default_style", style);
    form.append("is_real_person", String(real));
    form.append("source", file);
    try {
      await createCharacter(form);
      setName("");
      if (fileRef.current) fileRef.current.value = "";
      setChars(await listCharacters());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the avatar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="wrap">
      <header className="top">
        <div>
          <p className="eyebrow">contentforge</p>
          <h1>Avatars</h1>
        </div>
        <a className="btn" href="/studio">To studio →</a>
      </header>

      <div className="grid">
        <section className="panel">
          <p className="label">New avatar</p>
          <input className="field" placeholder="Name (e.g. Aria)" value={name}
            onChange={(e) => setName(e.target.value)} style={{ marginTop: 8 }} />
          <label className="label" style={{ marginTop: 12 }}>Look</label>
          <select className="field" value={style} onChange={(e) => setStyle(e.target.value)}>
            {STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <label className="checkrow">
            <input type="checkbox" checked={real} onChange={(e) => setReal(e.target.checked)} />
            This is a real person (renders as live video)
          </label>
          <label className="label" style={{ marginTop: 12 }}>Photo</label>
          <input ref={fileRef} className="field" type="file" accept="image/*" />
          <button className="btn primary" onClick={create} disabled={busy}
            style={{ width: "100%", marginTop: 16 }}>
            {busy ? "Creating…" : "Create avatar"}
          </button>
          {error && <p className="err">{error}</p>}
        </section>

        <section className="panel">
          <p className="label">Your avatars</p>
          {chars.length === 0 ? (
            <p className="empty">None yet. Create your first on the left.</p>
          ) : (
            <ul className="list">
              {chars.map((c) => (
                <li key={c.id} className="row">
                  <span className="cname">{c.name}</span>
                  <span className="cmeta">{c.default_style}{c.is_real_person ? " · real" : ""}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <style jsx>{`
        .wrap { max-width: 900px; margin: 0 auto; padding: 28px 24px 60px; }
        .top { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 22px; }
        h1 { font-size: 26px; font-weight: 700; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }
        @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
        .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 18px; }
        .checkrow { display: flex; gap: 8px; align-items: center; font-size: 13px; color: var(--muted); margin-top: 12px; }
        .empty { color: var(--muted); font-size: 13px; }
        .list { list-style: none; display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
        .row { display: flex; justify-content: space-between; padding: 10px 12px; background: var(--surface-2);
          border: 1px solid var(--border); border-radius: 8px; }
        .cname { font-weight: 500; }
        .cmeta { font-family: var(--mono); font-size: 11px; color: var(--faint); }
        .err { color: var(--rose); font-size: 13px; margin-top: 10px; }
      `}</style>
    </main>
  );
}
