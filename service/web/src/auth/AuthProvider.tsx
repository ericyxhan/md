import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import * as api from "../lib/api";
import type { SessionInfo } from "../lib/types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  session: SessionInfo | null;
  error: string | null;
  signIn: (password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const refresh = useCallback(async () => {
    try {
      const info = await api.getSession();
      setSession(info);
      setStatus(info.authenticated ? "authenticated" : "anonymous");
      setError(null);
    } catch (cause) {
      setSession(null);
      setStatus("anonymous");
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not reach the simulation service",
      );
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onUnauthorized = () => {
      setSession(null);
      setStatus("anonymous");
      queryClient.clear();
    };
    window.addEventListener("md:unauthorized", onUnauthorized);
    return () =>
      window.removeEventListener("md:unauthorized", onUnauthorized);
  }, [refresh, queryClient]);

  const signIn = useCallback(
    async (password: string) => {
      const info = await api.login(password);
      setSession(info);
      setStatus("authenticated");
      setError(null);
      await queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setSession(null);
      setStatus("anonymous");
      queryClient.clear();
    }
  }, [queryClient]);

  const value = useMemo(
    () => ({ status, session, error, signIn, signOut, refresh }),
    [status, session, error, signIn, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
