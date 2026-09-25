'use client';

/**
 * The entrance tween every chart shares, in one place.
 *
 * A hook rather than three props spread at each call site, and the reason is
 * the failure mode it removes: `isAnimationActive={!reduced}` has to be
 * remembered on every `<Line>`, `<Area>`, `<Bar>` and `<Pie>` a new chart
 * adds, and forgetting it animates for someone who asked their operating
 * system for stillness. Nothing reports that. Returning the three props as
 * an object means a new chart spreads one thing and cannot forget the other
 * two.
 *
 * It is also directly testable, which `isAnimationActive` on a Recharts
 * internal is not.
 */

import { useReducedMotion } from '@/hooks/use-reduced-motion';

import { CHART_ANIMATION_MS } from './chart-colors';

export interface ChartAnimation {
  isAnimationActive: boolean;
  animationDuration: number;
  animationEasing: 'ease-out';
}

export function useChartAnimation(): ChartAnimation {
  const reduced = useReducedMotion();
  return {
    isAnimationActive: !reduced,
    animationDuration: CHART_ANIMATION_MS,
    animationEasing: 'ease-out',
  };
}
