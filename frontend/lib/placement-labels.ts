/**
 * How a placement's status is named and coloured.
 *
 * Its own file rather than another entry in `lib/labels.ts`: that file is
 * already 800 lines of every domain's vocabulary, and placement is a module
 * somebody should be able to read end to end.
 *
 * Colour means state, per the design system: `success` for an offer that
 * became a job, `warning` for one still in the air, `neutral` for one that is
 * over. "Declined by the student" is not an error — somebody choosing a
 * different job is a normal outcome, and painting it red would read as a
 * failure the institute should answer for.
 */
import type { PlacementStatus } from '@/types/api';

export const PLACEMENT_STATUS_LABEL: Record<PlacementStatus, string> = {
  offered: 'Offered',
  accepted: 'Accepted',
  joined: 'Joined',
  declined: 'Declined',
  withdrawn: 'Withdrawn',
};

export const PLACEMENT_STATUS_VARIANT: Record<
  PlacementStatus,
  'neutral' | 'success' | 'warning' | 'error'
> = {
  offered: 'warning',
  accepted: 'success',
  joined: 'success',
  declined: 'neutral',
  withdrawn: 'neutral',
};

export const PLACEMENT_STATUS_OPTIONS: { value: PlacementStatus; label: string }[] = (
  Object.keys(PLACEMENT_STATUS_LABEL) as PlacementStatus[]
).map((value) => ({ value, label: PLACEMENT_STATUS_LABEL[value] }));
