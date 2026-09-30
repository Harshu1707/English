"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  TOKEN_STORAGE_KEY,
  UNAUTHORIZED_EVENT,
  authApi,
  clearToken,
  getToken,
  setToken,
  type RegisterInput,
  type User,
} from "../lib/api";

type AuthState = {
  user: User | null;
  /** true until we know whether a stored token is still valid */
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore the session: a stored token is only trusted once the server has accepted it.
  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    authApi
      .me()
      .then((u) => !cancelled && setUser(u))
      .catch(() => {
        clearToken();
        if (!cancelled) setUser(null);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  // Any API call that comes back 401 (expired/invalid token) signs the user out everywhere.
  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    const onStorage = (e: StorageEvent) => {
      if (e.key === TOKEN_STORAGE_KEY && !e.newValue) setUser(null); // signed out in another tab
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const finish = useCallback(async (res: { access_token: string; user: User | null }) => {
    setToken(res.access_token);
    const u = res.user ?? (await authApi.me());
    setUser(u);
    return u;
  }, []);

  const login = useCallback((email: string, password: string) => authApi.login(email, password).then(finish), [finish]);
  const register = useCallback((input: RegisterInput) => authApi.register(input).then(finish), [finish]);
  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** First name of the signed-in user, for greetings. */
export function FirstName({ fallback = "there" }: { fallback?: string }) {
  const { user } = useAuth();
  return <>{user?.full_name.trim().split(/\s+/)[0] || fallback}</>;
}
