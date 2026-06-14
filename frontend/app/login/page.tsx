"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { auth, login, register } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      const result =
        mode === "login" ? await login(email, password) : await register(email, password);
      auth.set(result.access_token);
      router.push("/studio");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="wrap">
      <div className="card">
        <p className="eyebrow">contentforge</p>
        <h1>{mode === "login" ? "Sign in" : "Create your account"}</h1>
        <p className="sub">Direct films in conversation. Watch them take shape.</p>

        <label className="label">Email</label>
        <input
          className="field"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <label className="label" style={{ marginTop: 12 }}>
          Password
        </label>
        <input
          className="field"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />

        <button className="btn primary go" onClick={submit} disabled={busy}>
          {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
        {error && <p className="err">{error}</p>}

        <p className="switch">
          {mode === "login" ? "No account yet?" : "Already have one?"}{" "}
          <button
            className="link"
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login" ? "Create one" : "Sign in"}
          </button>
        </p>
      </div>

      <style jsx>{`
        .wrap {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 24px;
        }
        .card {
          width: 100%;
          max-width: 380px;
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 32px;
        }
        h1 {
          font-size: 24px;
          font-weight: 700;
          margin: 4px 0 6px;
        }
        .sub {
          color: var(--muted);
          font-size: 13.5px;
          margin-bottom: 22px;
        }
        .label {
          display: block;
          margin-bottom: 6px;
        }
        .go {
          width: 100%;
          margin-top: 20px;
        }
        .err {
          color: var(--rose);
          font-size: 13px;
          margin-top: 12px;
        }
        .switch {
          margin-top: 18px;
          font-size: 13px;
          color: var(--muted);
          text-align: center;
        }
        .link {
          background: none;
          border: none;
          color: var(--amber);
          font-size: 13px;
        }
      `}</style>
    </main>
  );
}
