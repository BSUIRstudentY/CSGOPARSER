import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";

import { ApiError } from "../api";
import { useAuth } from "../auth";

export function LoginPage() {
  const { user, login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("admin@localhost");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-md rounded-lg border border-line bg-panel p-6">
      <p className="text-xs uppercase tracking-[0.2em] text-gold">Local desk</p>
      <h1 className="mt-2 text-2xl font-medium">CS2 Trading Bot</h1>
      <p className="mt-2 text-sm text-muted">
        Сравнение цен одного скина на разных площадках: где он дешевле и на сколько.
      </p>
      <form onSubmit={submit} className="mt-6 space-y-3">
        <label className="block text-sm">
          Email
          <input
            className="mt-1 w-full rounded border border-line bg-ink px-3 py-2"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            type="email"
            required
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            className="mt-1 w-full rounded border border-line bg-ink px-3 py-2"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            minLength={8}
            required
          />
        </label>
        {error && <p className="text-sm text-loss">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-gold px-3 py-2 font-medium text-ink disabled:opacity-60"
        >
          {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
      <button
        type="button"
        className="mt-4 text-sm text-muted underline"
        onClick={() => setMode(mode === "login" ? "register" : "login")}
      >
        {mode === "login" ? "Need an account?" : "Already registered?"}
      </button>
    </div>
  );
}
