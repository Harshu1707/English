"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { Brand } from "./SiteShell";
import { useAuth } from "./AuthProvider";
import { EXPIRED_FLAG, type Role } from "../lib/api";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Only ever redirect to a path inside this app (never //host or a full URL). */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return "/dashboard";
  if (raw.startsWith("/login") || raw.startsWith("/register")) return "/dashboard";
  return raw;
}

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { user, loading, login, register } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [role, setRole] = useState<Role>("teacher");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [next, setNext] = useState("/dashboard");

  useEffect(() => {
    setNext(safeNext(new URLSearchParams(window.location.search).get("next")));
    try {
      if (window.sessionStorage.getItem(EXPIRED_FLAG)) {
        window.sessionStorage.removeItem(EXPIRED_FLAG);
        setNotice("Your session has ended. Please sign in again.");
      }
    } catch { /* storage unavailable */ }
  }, []);

  useEffect(() => { if (!loading && user) router.replace(next); }, [loading, user, next, router]);

  function validate(): string {
    if (mode === "register" && fullName.trim().length < 2) return "Please enter your full name.";
    if (!EMAIL_RE.test(email.trim())) return "Please enter a valid email address.";
    if (mode === "register") {
      if (password.length < 12) return "Password must be at least 12 characters.";
      if (password !== confirm) return "Passwords do not match.";
      if (role === "admin" && !inviteCode.trim()) return "Admin accounts need an invite code.";
    } else if (!password) return "Please enter your password.";
    return "";
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setNotice("");
    const problem = validate();
    if (problem) { setError(problem); return; }
    setError("");
    setBusy(true);
    try {
      if (mode === "login") await login(email.trim(), password);
      else await register({ full_name: fullName.trim(), email: email.trim(), password, confirm_password: confirm, role, admin_invite_code: role === "admin" ? inviteCode.trim() : undefined });
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  const isLogin = mode === "login";
  return (
    <div className="auth-page">
      <header className="auth-top"><Brand /></header>
      <main className="auth-card card">
        <p className="eyebrow">{isLogin ? "WELCOME BACK" : "JOIN VERBA"}</p>
        <h1>{isLogin ? "Sign in to keep practising." : "Create your account."}</h1>
        <p className="auth-lede">{isLogin ? "Pick up your lessons and speaking practice where you left off." : "A calm space to develop your British English speaking voice."}</p>
        {notice && <p className="form-notice" role="status">{notice}</p>}
        <form onSubmit={submit} noValidate>
          {!isLogin && (
            <div className="field"><label htmlFor="full_name">Full name</label>
              <input id="full_name" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={150} /></div>
          )}
          <div className="field"><label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={255} /></div>
          <div className="field"><label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete={isLogin ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} maxLength={128} />
            {!isLogin && <small>At least 12 characters.</small>}</div>
          {!isLogin && (
            <>
              <div className="field"><label htmlFor="confirm_password">Confirm password</label>
                <input id="confirm_password" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} maxLength={128} /></div>
              <div className="field"><label htmlFor="role">Role</label>
                <select id="role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                  <option value="teacher">Teacher</option><option value="admin">Admin</option></select></div>
              {role === "admin" && (
                <div className="field"><label htmlFor="invite">Admin invite code</label>
                  <input id="invite" type="password" autoComplete="off" value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} maxLength={200} />
                  <small>Provided by your administrator.</small></div>
              )}
            </>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button auth-submit" type="submit" disabled={busy}>
            {busy ? (isLogin ? "Signing in…" : "Creating account…") : (isLogin ? "Sign in" : "Create account")} {!busy && <ArrowRight size={16} />}
          </button>
        </form>
        <p className="auth-alt">
          {isLogin ? "New to Verba? " : "Already have an account? "}
          <Link className="text-link" href={isLogin ? "/register" : "/login"}>{isLogin ? "Create an account" : "Sign in"}</Link>
        </p>
      </main>
    </div>
  );
}
