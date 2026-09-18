import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

/**
 * jsdom implements none of the browser APIs the motion layer (and, since
 * this phase, the chart layer) is built on, and each fails as a bare
 * `ReferenceError` from inside a third-party module — which reads like a
 * broken component rather than a missing environment.
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

/**
 * Recharts' `ResponsiveContainer` (every chart in `components/ui/charts/`)
 * sizes itself from a `ResizeObserver` — with none, it never learns a
 * non-negative width and never renders its children at all
 * (`ResponsiveContainerContextProvider` bails out on a negative initial
 * dimension), which would silently make every chart test assert on an empty
 * `<div>`. Reports a fixed, comfortably-plottable size the instant a chart
 * asks, the same "answer immediately" shape as the `IntersectionObserver`
 * stub above.
 */
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ImmediateResizeObserver implements ResizeObserver {
    constructor(private readonly callback: ResizeObserverCallback) {}

    observe(target: Element): void {
      const contentRect = {
        width: 600,
        height: 300,
        top: 0,
        left: 0,
        right: 600,
        bottom: 300,
        x: 0,
        y: 0,
        toJSON() {
          return this;
        },
      } as DOMRectReadOnly;
      this.callback([{ target, contentRect } as unknown as ResizeObserverEntry], this);
    }

    unobserve(): void {}
    disconnect(): void {}
  }

  globalThis.ResizeObserver = ImmediateResizeObserver as unknown as typeof ResizeObserver;
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
