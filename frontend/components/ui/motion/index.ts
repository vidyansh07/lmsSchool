/**
 * The animated layer, in one import.
 *
 * These are the pieces the dashboards are built from. Everything here is
 * client-side and reduced-motion aware; nothing here is required for the page
 * to be usable, which is the rule that keeps the motion honest — if removing
 * an animation would cost a person information, the information was in the
 * wrong place.
 */

export { BentoGrid, BentoTile } from './bento';
export { MotionProvider } from './motion-config';
export { NumberTicker } from './number-ticker';
export { ProgressRing } from './progress-ring';
export { Reveal } from './reveal';
export { Sparkline } from './sparkline';
export { SpotlightCard } from './spotlight-card';
export { StatCard } from './stat-card';
export type { StatCardProps } from './stat-card';
export { useReducedMotion } from './use-reduced-motion';
