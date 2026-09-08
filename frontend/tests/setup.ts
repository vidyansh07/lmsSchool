import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

/**
 * jsdom implements neither of the two browser APIs the motion layer is built
 * on, and both fail as a bare `ReferenceError` from inside a third-party
 * module — which reads like a broken component rather than a missing
 * environment.
 *
 * `IntersectionObserver` decides when a `Reveal` or a `NumberTicker` has
 * entered the viewport. The stub reports every observed element as visible
 * straight away: under test there is no viewport and no scrolling, so
 * "on screen" is the only answer that lets assertions see the final content
 * rather than an element waiting forever to be revealed.
 *
 * `matchMedia` answers the reduced-motion query. It reports no preference, so
 * tests exercise the same path the majority of people get; a test that cares
 * about the reduced-motion branch stubs it itself.
 */
if (typeof globalThis.IntersectionObserver === 'undefined') {
  class ImmediateIntersectionObserver implements IntersectionObserver {
    readonly root = null;
    readonly rootMargin = '';
    readonly thresholds: ReadonlyArray<number> = [];

    constructor(private readonly callback: IntersectionObserverCallback) {}

    observe(target: Element): void {
      this.callback(
        [{ isIntersecting: true, target, intersectionRatio: 1 } as IntersectionObserverEntry],
        this,
      );
    }

    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }

  globalThis.IntersectionObserver = ImmediateIntersectionObserver as unknown as typeof IntersectionObserver;
}

if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  // Cookies leak between tests otherwise, which would hide CSRF bugs.
  document.cookie.split('; ').forEach((entry) => {
    const name = entry.split('=')[0];
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  });
});
