"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, isTokenExpired, tokenStore, UNAUTHORIZED_EVENT } from "./api";
import type { TokenResponse, User } from "./types";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  user: User | null;
  status: Status;
  /** True when the session ended because the token expired or was rejected. */
  expired: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [expired, setExpired] = useState(false);

  const endSession = useCallback((wasExpired: boolean) => {
    tokenStore.clear();
    setUser(null);
    setStatus("anonymous");
    setExpired(wasExpired);
  }, []);

  useEffect(() => {
    const token = tokenStore.get();
    if (!token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- session is read from localStorage after mount
      setStatus("anonymous");
      return;
    }
    if (isTokenExpired(token)) {
      endSession(true);
      return;
    }
    api.auth
      .me()
      .then((u) => {
        setUser(u);
        setStatus("authenticated");
      })
      .catch(() => endSession(true));
  }, [endSession]);

  useEffect(() => {
    const onUnauthorized = () => endSession(true);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    // Proactively end the session when the JWT expires while the tab is open.
    const timer = setInterval(() => {
      const token = tokenStore.get();
      if (token && isTokenExpired(token)) endSession(true);
    }, 60_000);
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
      clearInterval(timer);
    };
  }, [endSession]);

  const accept = useCallback(async (res: TokenResponse) => {
    tokenStore.set(res.access_token);
    // /auth/me may carry fields (e.g. nexconn_token) that the login response omits.
    const fresh = await api.auth.me().catch(() => res.user);
    setUser({ ...res.user, ...fresh });
    setExpired(false);
    setStatus("authenticated");
  }, []);

  const value: AuthContextValue = {
    user,
    status,
    expired,
    login: async (email, password) => accept(await api.auth.login({ email, password })),
    register: async (name, email, password) => accept(await api.auth.register({ name, email, password })),
    logout: () => endSession(false),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
