'use client';

/**
 * The motion runtime, loaded once and lazily.
 *
 * `LazyMotion` with `domAnimation` is the small half of the library: it can
 * animate transforms, opacity, colours and layout, which is everything this
 * product does. The other half — SVG path morphing, 3d, drag physics — is a
 * chunk this app would download and never call. Components under here use `m`
 * rather than `motion` for the same reason: `motion.div` pulls the full
 * feature set in at the import, and `m.div` takes it from this provider.
 *
 * `strict` makes that a build error rather than a silent 20KB.
 */

import { domAnimation, LazyMotion, MotionConfig } from 'motion/react';
import type { ReactNode } from 'react';

import { useReducedMotion } from './use-reduced-motion';

export function MotionProvider({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();

  return (
    <LazyMotion features={domAnimation} strict>
      {/* "user" would re-read the media query itself; passing the resolved
          value keeps one source of truth with the CSS and with every hook
          below, so a component cannot disagree with the stylesheet. */}
      <MotionConfig reducedMotion={reduced ? 'always' : 'never'}>{children}</MotionConfig>
    </LazyMotion>
  );
}
