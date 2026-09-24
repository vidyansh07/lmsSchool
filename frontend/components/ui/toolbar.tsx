import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * The filter and action strip that sits above a list.
 *
 * Layout only, and hook-free on purpose. `components/ui/*` is entirely
 * directive-free, and adding `'use client'` to one file here pulls every server
 * component that renders it into the client graph with no error and no test to
 * catch it. So the search box — which needs `useId()` so two toolbars on one
 * page do not collide — stays in `components/list-toolbar.tsx`, which is
 * already a client component, and only the shell lives here.
 *
 * `items-end` rather than `items-center`: the controls in this strip are a
 * mixture of labelled fields and bare buttons, and aligning them on their
 * baseline is the only arrangement where a button lines up with the input
 * beside it rather than with the input's label.
 *
 * There is deliberately no `ToolbarGroup`. Every filter strip in the app hands
 * its controls to `ListToolbar` as siblings and wants them to wrap
 * independently, so a cluster that must not be split is a shape nothing has
 * asked for yet. It is four lines to add back the day something does, and
 * until then a second spelling of "a flex row of controls" is the drift this
 * file exists to end.
 */
export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('flex flex-wrap items-end gap-2', className)}>{children}</div>;
}
