// The curator's own COCONUT login. The password lives only in this form's state and goes to
// COCONUT through the MARCUS server's relay, which neither stores nor logs it.
import { useRef, useState, type FormEvent } from "react";
import { GlassButton } from "../ui/GlassButton";
import { CoconutLoginError, coconutLogin } from "./coconutApi";
import "./coconut.css";

type CoconutLoginProps = {
  onLoggedIn: (token: string) => void;
  /** Email takes focus (the batch dialog, where the login comes first); not at a form's end. */
  autoFocus?: boolean;
};

export default function CoconutLogin({ onLoggedIn, autoFocus = true }: CoconutLoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busyNow = useRef(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busyNow.current || !email.trim() || !password) return;
    busyNow.current = true;
    setBusy(true);
    setError(null);
    try {
      const token = await coconutLogin(email.trim(), password);
      setPassword("");
      onLoggedIn(token);
    } catch (err) {
      setError(err instanceof CoconutLoginError ? err.message : "Could not log in");
    } finally {
      busyNow.current = false;
      setBusy(false);
    }
  }

  return (
    <form className="coconut-login" onSubmit={(e) => void submit(e)} aria-busy={busy}>
      <h3 className="coconut-login__title">Log in to COCONUT</h3>
      <p className="coconut-login__note">Your own COCONUT account. The login stays in this tab.</p>
      <div className="coconut-field">
        <label className="mono-label coconut-field__label" htmlFor="coconut-email">
          Email
        </label>
        <input
          id="coconut-email"
          className="coconut-input"
          type="email"
          autoComplete="username"
          autoFocus={autoFocus}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>
      <div className="coconut-field">
        <label className="mono-label coconut-field__label" htmlFor="coconut-password">
          Password
        </label>
        <input
          id="coconut-password"
          className="coconut-input"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      {error ? (
        <p className="coconut-login__error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="coconut-login__actions">
        <GlassButton tint="green" type="submit" disabled={busy || !email.trim() || !password}>
          Log in
        </GlassButton>
        <a href="https://coconut.naturalproducts.net/register" target="_blank" rel="noopener noreferrer">
          No account?
        </a>
      </div>
    </form>
  );
}
