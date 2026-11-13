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
import type { SessionInfo, UserInfo } from "../lib/types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  session: SessionInfo | null;
  user: UserInfo | null;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (payload: api.RegisterPayload) => Promise<void>;
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
    async (email: string, password: string) => {
      const info = await api.login(email, password);
      setSession(info);
      setStatus("authenticated");
      setError(null);
      await queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const signUp = useCallback(
    async (payload: api.RegisterPayload) => {
      const account = await api.register(payload);
      // The server signs the new account in; read the session back so the
      // console shows the same state a returning user would get.
      const info = await api.getSession();
      setSession(
        info.authenticated ? info : { authenticated: true, user: account },
      );
      setStatus("authenticated");
      setError(null);
      await queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // The local session is cleared either way; a failed logout request
      // must not surface as an unhandled rejection.
    } finally {
      setSession(null);
      setStatus("anonymous");
      queryClient.clear();
    }
  }, [queryClient]);

  const value = useMemo(
    () => ({
      status,
      session,
      user: session?.user ?? null,
      error,
      signIn,
      signUp,
      signOut,
      refresh,
    }),
    [status, session, error, signIn, signUp, signOut, refresh],
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
