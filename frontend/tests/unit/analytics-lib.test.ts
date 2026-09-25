/**
 * The client-side arithmetic behind the analytics charts.
 *
 * Worth testing directly rather than through a rendered chart: a chart draws
 * whatever it is handed, so an error in a merge or a bucket is invisible on
 * screen until somebody checks the figure against the ledger.
 *
 * The property every case below is really about is that **a missing value
 * stays missing**. The backend returns `null` rather than `0` for an empty
 * denominator on purpose, and anything that quietly turned that into a zero
 * would put a floor on a chart that should show a gap.
 */

import { describe, expect, it } from 'vitest';

import {
  ageingBuckets,
  heldAgainstAttendance,
  mergeByWeek,
  money,
  withCumulative,
} from '@/lib/analytics';

describe('mergeByWeek', () => {
  it('lines two series up on their shared week', () => {
    const merged = mergeByWeek([
      { rows: [{ week: '2026-01-05', held: 12 }], keys: ['held'] },
      { rows: [{ week: '2026-01-05', percent: 82 }], keys: ['percent'] },
    ]);
    expect(merged).toEqual([{ date: '2026-01-05', held: 12, percent: 82 }]);
  });

  it('leaves a week missing from one series undefined, not zero', () => {
    // A week with classes but no enrolments is normal. A chart draws a gap
    // for undefined and a floor for 0, and only one of those is true.
    const merged = mergeByWeek([
      { rows: [{ week: '2026-01-05', held: 12 }, { week: '2026-01-12', held: 9 }], keys: ['held'] },
      { rows: [{ week: '2026-01-05', percent: 82 }], keys: ['percent'] },
    ]);
    expect(merged[1]).toEqual({ date: '2026-01-12', held: 9 });
    expect(merged[1]).not.toHaveProperty('percent', 0);
  });

  it('carries a null straight through', () => {
    const merged = mergeByWeek([
      { rows: [{ week: '2026-01-05', percent: null }], keys: ['percent'] },
    ]);
    expect(merged[0]?.percent).toBeNull();
  });

  it('sorts weeks chronologically without parsing a date', () => {
    // ISO week keys sort lexically and chronologically at once, so there is
    // no timezone in the middle of the chart.
    const merged = mergeByWeek([
      {
        rows: [
          { week: '2026-02-02', held: 3 },
          { week: '2026-01-05', held: 1 },
          { week: '2026-01-12', held: 2 },
        ],
        keys: ['held'],
      },
    ]);
    expect(merged.map((row) => row.date)).toEqual(['2026-01-05', '2026-01-12', '2026-02-02']);
  });

  it('turns an unparseable value into null rather than NaN', () => {
    // `crawl.spec.ts` fails on the literal string NaN appearing on a page,
    // which is how this would otherwise surface.
    const merged = mergeByWeek([
      { rows: [{ week: '2026-01-05', held: 'not a number' }], keys: ['held'] },
    ]);
    expect(merged[0]?.held).toBeNull();
  });

  it('ignores a row with no week at all', () => {
    const merged = mergeByWeek([{ rows: [{ held: 4 }], keys: ['held'] }]);
    expect(merged).toEqual([]);
  });
});

describe('withCumulative', () => {
  it('runs a total alongside the period figure', () => {
    const rows = withCumulative(
      [
        { date: '2026-01-05', amount: 100 },
        { date: '2026-01-12', amount: 250 },
        { date: '2026-01-19', amount: 50 },
      ],
      'amount',
    );
    expect(rows.map((row) => row.cumulative)).toEqual([100, 350, 400]);
  });

  it('holds the running total across a missing period', () => {
    // A week with no takings did not reset the year's collections.
    const rows = withCumulative(
      [
        { date: '2026-01-05', amount: 100 },
        { date: '2026-01-12', amount: null },
        { date: '2026-01-19', amount: 50 },
      ],
      'amount',
    );
    expect(rows.map((row) => row.cumulative)).toEqual([100, 100, 150]);
  });

  it('keeps the source rows intact', () => {
    const rows = withCumulative([{ date: '2026-01-05', amount: 100 }], 'amount');
    expect(rows[0]).toMatchObject({ date: '2026-01-05', amount: 100, cumulative: 100 });
  });
});

describe('money', () => {
  it('reads the decimal strings the API sends', () => {
    expect(money('2500.00')).toBe(2500);
    expect(money('0.00')).toBe(0);
  });

  it('is null for anything that is not an amount', () => {
    expect(money(null)).toBeNull();
    expect(money(undefined)).toBeNull();
    expect(money('')).toBeNull();
    expect(money('  ')).toBeNull();
    expect(money('not money')).toBeNull();
    expect(money(Number.NaN)).toBeNull();
  });
});

describe('ageingBuckets', () => {
  const TODAY = '2026-03-01';

  it('sorts overdue plans by how late they are', () => {
    const buckets = ageingBuckets(
      [
        { next_due_on: '2026-02-26' }, // 3 days
        { next_due_on: '2026-02-10' }, // 19 days
        { next_due_on: '2026-01-15' }, // 45 days
        { next_due_on: '2025-10-01' }, // 151 days
      ],
      TODAY,
    );
    expect(buckets.map((bucket) => bucket.value)).toEqual([1, 1, 1, 1]);
  });

  it('excludes anything that is not actually late', () => {
    // A plan due today or tomorrow is not one-to-seven-days late, and
    // putting it in that bucket would make the first bar a lie.
    const buckets = ageingBuckets(
      [{ next_due_on: '2026-03-01' }, { next_due_on: '2026-03-20' }, { next_due_on: null }],
      TODAY,
    );
    expect(buckets.every((bucket) => bucket.value === 0)).toBe(true);
  });

  it('always returns every bucket, so the chart keeps its shape', () => {
    const buckets = ageingBuckets([], TODAY);
    expect(buckets).toHaveLength(4);
    expect(buckets.map((bucket) => bucket.label)).toEqual([
      '1–7 days',
      '8–30 days',
      '31–90 days',
      'Over 90 days',
    ]);
  });

  it('counts a plan due yesterday as one day late whatever the clock says', () => {
    const buckets = ageingBuckets([{ next_due_on: '2026-02-28' }], TODAY);
    expect(buckets[0]?.value).toBe(1);
  });
});

describe('heldAgainstAttendance', () => {
  it('pairs the count with the rate on the shared week', () => {
    const merged = heldAgainstAttendance(
      [{ week: '2026-01-05', scheduled: 14, held: 12, cancelled: 1, registers_outstanding: 2 }],
      [{ week: '2026-01-05', counted: 40, attended: 33, percent: 82.5 }],
    );
    expect(merged).toEqual([
      { date: '2026-01-05', held: 12, registers_outstanding: 2, percent: 82.5 },
    ]);
  });

  it('keeps a week with classes but no register readable', () => {
    const merged = heldAgainstAttendance(
      [{ week: '2026-01-05', scheduled: 4, held: 4, cancelled: 0, registers_outstanding: 4 }],
      [{ week: '2026-01-05', counted: 0, attended: 0, percent: null }],
    );
    expect(merged[0]?.percent).toBeNull();
    expect(merged[0]?.held).toBe(4);
  });
});
