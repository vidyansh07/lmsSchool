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
  useState,
  type ReactNode,
} from 'react';

import { ApiError } from '@/lib/api';
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
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

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
  }, []);

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
  }, []);

  const signOut = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      isLoading,
      error,
      refresh: load,
      signOut,
      setUser,
      can: (capability: CapabilityName) => can(user?.capabilities, capability),
    }),
    [user, isLoading, error, load, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>.');
  return context;
}
