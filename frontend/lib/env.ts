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

/** Names that mean "the machine this code is running on", which is the whole
 *  problem: on the server that is the developer's laptop, and in a browser it
 *  is whatever machine is holding the browser. */
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1', '0.0.0.0']);

/**
 * The API origin as the browser should reach it.
 *
 * `NEXT_PUBLIC_API_BASE_URL` is baked in at build time, and locally it says
 * `http://localhost:8000`. That is correct for exactly one visitor: someone
 * whose browser is on the same machine *and* who typed `localhost`. Reach the
 * same dev server as `127.0.0.1:3100`, by LAN address, or from a phone, and
 * the page tells that browser to call its own localhost — which is a different
 * machine, or at best a different site.
 *
 * Two things break there, and the second is the one that wastes an afternoon:
 * the API rejects the unlisted origin with no CORS header, and even once that
 * is allowed, a session cookie set on `localhost` is not sent from a page on
 * `127.0.0.1`, because those are separate sites as far as SameSite is
 * concerned. Sign-in appears to succeed and the next request is anonymous.
 *
 * So when the configured host is a loopback name and the page is being served
 * from somewhere else, keep the configured scheme and port and follow the
 * host the visitor actually used. A deployment whose API is a real hostname
 * never matches the loopback test, so this cannot fire in production.
 */
function browserApiBaseUrl(): string {
  const configured = env.publicApiBaseUrl;
  if (typeof window === 'undefined') return configured;

  let url: URL;
  try {
    url = new URL(configured);
  } catch {
    // A relative or malformed base means the API is same-origin. Leave it.
    return configured;
  }

  const pageHost = window.location.hostname;
  if (!LOOPBACK_HOSTS.has(url.hostname)) return configured;
  if (!pageHost || pageHost === url.hostname) return configured;

  url.hostname = pageHost;
  url.protocol = window.location.protocol;
  return trimTrailingSlash(url.toString());
}

/** Base URL to use from the current execution context. */
export function apiBaseUrl(): string {
  return env.isServer ? env.internalApiBaseUrl : browserApiBaseUrl();
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
