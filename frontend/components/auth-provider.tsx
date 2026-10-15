'use client';

/**
 * Session state for the interface.
 *
 * The session itself lives in an HttpOnly cookie the browser cannot read, so
 * "who am I?" is answered by asking the server once on mount and caching the
 * answer for rendering. Nothing here is a security boundary — it decides what
 * to *show*, while the backend decides what is *allowed*.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { ApiError, onSessionEnded } from '@/lib/api';
import { fetchCurrentUser, logout as apiLogout } from '@/lib/auth';
import { can, type CapabilityName } from '@/lib/capabilities';
import type { CurrentUser } from '@/types/api';

interface AuthState {
  user: CurrentUser | null;
  isLoading: boolean;
  error: ApiError | null;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
  setUser: (user: CurrentUser | null) => void;
  can: (capability: CapabilityName) => boolean;
  /** True after a signed-in session was ended by the server (expired or
   *  revoked), until somebody signs in again — the sign-in page says so. */
  sessionEnded: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const signedIn = useRef(false);

  useEffect(() => {
    signedIn.current = user !== null;
  }, [user]);

  // Any request answered `authentication_required` while somebody is signed
  // in means the session is gone. Forgetting the user lets `RequireAuth` send
  // them to sign-in with `?next=` pointing back at this page. Ignored for a
  // visitor who was never signed in — that answer is how they are detected.
  useEffect(
    () =>
      onSessionEnded(() => {
        if (!signedIn.current) return;
        signedIn.current = false;
        setSessionEnded(true);
        setUserState(null);
      }),
    [],
  );

  const setUser = useCallback((next: CurrentUser | null) => {
    if (next) setSessionEnded(false);
    setUserState(next);
  }, []);

  const load = useCallback(async () => {
    try {
      setUser(await fetchCurrentUser());
      setError(null);
    } catch (cause) {
      // 401/403 simply means "not signed in", which is not an error state.
      if (cause instanceof ApiError && (cause.status === 401 || cause.status === 403)) {
        setUser(null);
        setError(null);
      } else {
        setError(cause instanceof ApiError ? cause : null);
      }
    } finally {
      setIsLoading(false);
    }
  }, [setUser]);

  useEffect(() => {
    let cancelled = false;
    // Resolved asynchronously, so no state is set synchronously in the effect.
    fetchCurrentUser()
      .then((currentUser) => {
        if (!cancelled) setUser(currentUser);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        if (cause instanceof ApiError && (cause.status === 401 || cause.status === 403)) {
          setUser(null);
        } else {
          setError(cause instanceof ApiError ? cause : null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [setUser]);

  const signOut = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
    }
  }, [setUser]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      isLoading,
      error,
      refresh: load,
      signOut,
      setUser,
      can: (capability: CapabilityName) => can(user?.capabilities, capability),
      sessionEnded,
    }),
    [user, isLoading, error, load, signOut, setUser, sessionEnded],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>.');
  return context;
}
