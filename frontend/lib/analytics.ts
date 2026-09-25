/**
 * The small amount of arithmetic the analytics charts need on the client.
 *
 * Everything here is a pure function over API rows, kept out of the page
 * components so it can be tested directly -- a chart renders whatever it is
 * handed, so a bug in a merge or a bucket is invisible on screen until
 * someone checks the number against the ledger.
 *
 * The rule every function follows: **a missing value stays missing.** The
 * backend's `_percent` returns `null` rather than `0` for an empty
 * denominator, because "0% of nothing" reads as a failure when it means
 * there was nothing to measure. Anything that turned that `null` into a `0`
 * on the way to a chart would undo the whole point, so none of these do.
 */

import type { DeliveryTrendPoint, FeePlanBrief, TrendPoint } from '@/types/api';

/** The shape every chart in `components/ui/charts` wants for a time series. */
export interface WeeklyDatum {
  date: string;
  [key: string]: string | number | null | undefined;
}

/**
 * Line up two or more weekly series on their shared `week` key.
 *
 * The trend endpoints are separate calls that each group by `TruncWeek`, so
 * their keys align exactly -- but a week present in one and absent from the
 * other is normal (a week with classes but no enrolments, say). Those gaps
 * stay `undefined` rather than becoming zero: a chart draws a gap for the
 * first and a floor for the second, and only one of those is true.
 */
export function mergeByWeek(
  series: ReadonlyArray<{ rows: readonly object[]; keys: readonly string[] }>,
): WeeklyDatum[] {
  const byWeek = new Map<string, WeeklyDatum>();

  for (const { rows, keys } of series) {
    for (const source of rows) {
      // Read by key: the callers pass typed API rows, whose interfaces are
      // not assignable to an index signature even though every field is
      // readable.
      const row = source as Record<string, unknown>;
      const week = typeof row.week === 'string' ? row.week : null;
      if (!week) continue;
      const existing = byWeek.get(week) ?? { date: week };
      for (const key of keys) {
        const value = row[key];
        existing[key] =
          typeof value === 'number' || value === null ? value : Number(value ?? Number.NaN);
        if (Number.isNaN(existing[key] as number)) existing[key] = null;
      }
      byWeek.set(week, existing);
    }
  }

  // Sorted by the ISO week key, which sorts lexically and chronologically at
  // once -- no Date parsing, so no timezone in the middle of a chart.
  return [...byWeek.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * A running total alongside the per-period figure.
 *
 * Derived from the same rows the bars are drawn from rather than fetched
 * separately, so the line and the bars cannot disagree -- which is the whole
 * reason a "collected this period / collected to date" chart is worth
 * drawing at all.
 *
 * A `null` period contributes nothing and leaves the running total where it
 * was, rather than resetting it or turning it into `NaN`.
 */
export function withCumulative<T extends WeeklyDatum>(
  rows: readonly T[],
  sourceKey: string,
  cumulativeKey = 'cumulative',
): WeeklyDatum[] {
  let running = 0;
  return rows.map((row) => {
    const value = row[sourceKey];
    if (typeof value === 'number' && Number.isFinite(value)) running += value;
    return { ...row, [cumulativeKey]: running };
  });
}

/** A decimal-string money field, as the API sends it, to a number. */
export function money(value: string | number | null | undefined): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** The buckets an overdue fee falls into, oldest last. */
export const AGEING_BUCKETS = [
  { key: '0-7', label: '1–7 days', upTo: 7 },
  { key: '8-30', label: '8–30 days', upTo: 30 },
  { key: '31-90', label: '31–90 days', upTo: 90 },
  { key: '90+', label: 'Over 90 days', upTo: Number.POSITIVE_INFINITY },
] as const;

/**
 * Overdue plans grouped by how late they are.
 *
 * Days are counted from the ISO date strings directly rather than through
 * `Date` arithmetic on a timestamp, so a plan due yesterday is one day late
 * regardless of the reader's clock.
 *
 * Anything not actually overdue -- no due date, or a date in the future --
 * is excluded rather than dropped into the first bucket, which would make
 * "1-7 days late" include things that are not late at all.
 */
export function ageingBuckets(
  plans: readonly Pick<FeePlanBrief, 'next_due_on'>[],
  today: string = new Date().toISOString().slice(0, 10),
): { label: string; value: number }[] {
  const counts = new Map<string, number>(AGEING_BUCKETS.map((bucket) => [bucket.key, 0]));
  const now = Date.parse(`${today}T00:00:00Z`);

  for (const plan of plans) {
    if (!plan.next_due_on) continue;
    const due = Date.parse(`${plan.next_due_on}T00:00:00Z`);
    if (!Number.isFinite(due)) continue;
    const days = Math.floor((now - due) / 86_400_000);
    if (days < 1) continue;
    const bucket = AGEING_BUCKETS.find((candidate) => days <= candidate.upTo);
    if (bucket) counts.set(bucket.key, (counts.get(bucket.key) ?? 0) + 1);
  }

  return AGEING_BUCKETS.map((bucket) => ({
    label: bucket.label,
    value: counts.get(bucket.key) ?? 0,
  }));
}

/**
 * Attendance and delivery, merged for the dual-axis chart.
 *
 * Named rather than inlined at the three call sites that want it, because
 * the pairing is the same everywhere: classes held on the left axis, the
 * attendance rate on the right.
 */
export function heldAgainstAttendance(
  delivery: readonly DeliveryTrendPoint[],
  attendance: readonly TrendPoint[],
): WeeklyDatum[] {
  return mergeByWeek([
    { rows: delivery, keys: ['held', 'registers_outstanding'] },
    { rows: attendance, keys: ['percent'] },
  ]);
}
