'use client';

/**
 * Applies the institution's brand colour as early as the browser allows.
 *
 * Rendered at the top of `<body>`, before the shell and before any screen, so
 * the colour lands in the same paint as the first content rather than a beat
 * later. A brand that arrives second is worse than no brand at all: the page
 * flashes the default orange and then changes, which reads as a bug.
 *
 * The colour is read from `localStorage` first and from the server second. That
 * ordering is the whole point — the stored value is available synchronously and
 * is almost always right, while the API round trip cannot beat first paint no
 * matter how fast it is. The fetch then corrects the cache for next time, so a
 * change made on another device is picked up on the following load.
 *
 * Failing quietly is deliberate. If the settings endpoint is unreachable the
 * product should open in its default colours, not refuse to render — nobody has
 * ever been helped by an ERP that will not start because it could not confirm
 * what shade of orange to be.
 */

import { useEffect } from 'react';

import { apiFetch } from '@/lib/api';
import { applyBrandColor } from '@/lib/brand';

const CACHE_KEY = 'grras.brand-color';

interface BrandingResponse {
  brand_color: string | null;
}

export function BrandTheme() {
  useEffect(() => {
    // `localStorage` throws outright in a private window with site data blocked,
    // and returns null in plenty of ordinary cases. Neither is exceptional.
    try {
      const cached = window.localStorage.getItem(CACHE_KEY);
      if (cached) applyBrandColor(cached);
    } catch {
      // No cache available. The server value below still applies.
    }

    let cancelled = false;
    apiFetch<BrandingResponse>('/api/v1/branding/')
      .then((branding) => {
        if (cancelled) return;
        applyBrandColor(branding.brand_color);
        try {
          if (branding.brand_color) {
            window.localStorage.setItem(CACHE_KEY, branding.brand_color);
          } else {
            window.localStorage.removeItem(CACHE_KEY);
          }
        } catch {
          // Not being able to remember it is not a reason to fail applying it.
        }
      })
      .catch(() => {
        // Offline, signed out, or the endpoint is down. The default palette in
        // `globals.css` is a perfectly good product.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
