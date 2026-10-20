/**
 * `toISOString().slice(0, 10)` is the UTC day. In India that is yesterday
 * until 05:30, and for a date built at local midnight — the first of the
 * month — it is always the day before. `localIsoDate` is the viewer's day.
 */
import { describe, expect, it } from 'vitest';

import { localIsoDate, parseLocalIsoDate } from '@/lib/format';

describe('localIsoDate', () => {
  it('names the local calendar day, not the UTC one', () => {
    // Built from local parts, so it is local midnight on 1 October wherever
    // the test runs — exactly the case `toISOString` turned into 30 September
    // east of Greenwich.
    expect(localIsoDate(new Date(2026, 9, 1))).toBe('2026-10-01');
    expect(localIsoDate(new Date(2026, 9, 1, 0, 30))).toBe('2026-10-01');
    expect(localIsoDate(new Date(2026, 9, 1, 23, 59))).toBe('2026-10-01');
  });

  it('round-trips through parseLocalIsoDate', () => {
    expect(localIsoDate(parseLocalIsoDate('2026-02-28'))).toBe('2026-02-28');
    const next = parseLocalIsoDate('2026-02-28');
    next.setDate(next.getDate() + 1);
    expect(localIsoDate(next)).toBe('2026-03-01');
  });
});
