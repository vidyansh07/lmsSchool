/**
 * Environment access, validated once at module load.
 *
 * Reading `process.env` inline all over the codebase makes a missing variable
 * surface as a confusing runtime failure. Resolving it here means a
 * misconfigured deployment fails loudly and in one place.
 *
 * Only NEXT_PUBLIC_* values may be referenced from browser code; they are
 * inlined into the bundle and are therefore public by definition.
 */

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

const publicApiBaseUrl = trimTrailingSlash(
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000',
);

/**
 * Server components run inside the container network, where the backend is
 * reachable by service name rather than on the host's localhost.
 */
const internalApiBaseUrl = trimTrailingSlash(
  process.env.INTERNAL_API_BASE_URL ?? publicApiBaseUrl,
);

export const env = {
  publicApiBaseUrl,
  internalApiBaseUrl,
  appEnv: process.env.NEXT_PUBLIC_APP_ENV ?? 'local',
  isServer: typeof window === 'undefined',
} as const;

/** Base URL to use from the current execution context. */
export function apiBaseUrl(): string {
  return env.isServer ? env.internalApiBaseUrl : env.publicApiBaseUrl;
}

/**
 * Absolute URL for an API path the *browser* will resolve on its own.
 *
 * `apiFetch` prefixes the base itself, so it does not need this. An `<img
 * src>`, an `<a href>` or a `window.open` does: the browser resolves a bare
 * `/api/...` against the page's origin, which is the Next server, not the API.
 * The serializers return relative paths deliberately — they do not know the
 * public hostname — so composing the origin belongs here, on the client.
 */
export function apiUrl(path: string): string {
  if (/^[a-z][a-z0-9+.-]*:/i.test(path)) return path;
  return `${apiBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`;
}
