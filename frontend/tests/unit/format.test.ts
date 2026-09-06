import { describe, expect, it } from 'vitest';

import {
  fallback,
  formatCount,
  formatDate,
  formatDateTime,
  formatDuration,
  formatName,
  formatNumber,
  formatPercent,
  formatRelative,
  NO_DATA,
  NOT_ASSIGNED,
  NOT_AVAILABLE,
  NOT_SUBMITTED,
  UNKNOWN,
} from '@/lib/format';

/** Values every numeric/date formatter must survive without producing junk output. */
const HOSTILE_VALUES: unknown[] = [
  null,
  undefined,
  '',
  '   ',
  NaN,
  Infinity,
  -Infinity,
  'not a number',
  'not a date',
  new Date(Number.NaN),
];

/** Values the generic `fallback()` stringifier must treat as "nothing to show". */
const NULLISH_VALUES: unknown[] = [null, undefined, '', '   ', NaN, Infinity, -Infinity, new Date(Number.NaN)];

describe('fallback', () => {
  it('passes through a real value', () => {
    expect(fallback('Trainer name')).toBe('Trainer name');
    expect(fallback(42)).toBe('42');
  });

  it('passes through arbitrary non-empty text unchanged', () => {
    expect(fallback('not a number')).toBe('not a number');
    expect(fallback('not a date')).toBe('not a date');
  });

  it.each(NULLISH_VALUES)('falls back for %p', (value) => {
    expect(fallback(value)).toBe(NOT_AVAILABLE);
  });

  it('trims whitespace-only strings to the fallback', () => {
    expect(fallback('   ')).toBe(NOT_AVAILABLE);
  });

  it('accepts a custom label', () => {
    expect(fallback(null, NOT_ASSIGNED)).toBe(NOT_ASSIGNED);
  });

  it('does not fall back on 0 or false', () => {
    expect(fallback(0)).toBe('0');
    expect(fallback(false)).toBe('false');
  });
});

describe('formatNumber', () => {
  it('formats a finite number', () => {
    expect(formatNumber(1234)).toBe('1,234');
    expect(formatNumber(0)).toBe('0');
    expect(formatNumber('42')).toBe('42');
  });

  it.each(HOSTILE_VALUES)('falls back for %p', (value) => {
    expect(formatNumber(value)).toBe(NOT_AVAILABLE);
  });

  it('accepts a custom label and digit count', () => {
    expect(formatNumber(null, { fallbackLabel: NO_DATA })).toBe(NO_DATA);
    expect(formatNumber(1.2345, { maximumFractionDigits: 1 })).toBe('1.2');
  });
});

describe('formatPercent', () => {
  it('formats and rounds to whole percent by default', () => {
    expect(formatPercent(82.4)).toBe('82%');
    expect(formatPercent(0)).toBe('0%');
  });

  it.each(HOSTILE_VALUES)('falls back for %p', (value) => {
    expect(formatPercent(value)).toBe(NOT_AVAILABLE);
  });

  it('supports fraction digits', () => {
    expect(formatPercent(82.456, { maximumFractionDigits: 1 })).toBe('82.5%');
  });
});

describe('formatDate', () => {
  it('formats a valid ISO string, Date, and epoch', () => {
    expect(formatDate('2024-03-15')).toMatch(/2024/);
    expect(formatDate(new Date(2024, 2, 15))).toMatch(/2024/);
    // Epoch 0 is a real, valid date — it must render, not fall back.
    expect(formatDate(0)).not.toBe(NOT_AVAILABLE);
    expect(formatDate(new Date(0))).not.toBe(NOT_AVAILABLE);
  });

  it.each(HOSTILE_VALUES)('falls back for %p', (value) => {
    expect(formatDate(value)).toBe(NOT_AVAILABLE);
  });

  it('accepts a custom label', () => {
    expect(formatDate(null, NOT_SUBMITTED)).toBe(NOT_SUBMITTED);
  });

  it('never renders the literal "Invalid Date"', () => {
    for (const value of HOSTILE_VALUES) {
      expect(formatDate(value)).not.toMatch(/invalid date/i);
    }
  });
});

describe('formatDateTime', () => {
  it('formats a valid value with a time component', () => {
    expect(formatDateTime('2024-03-15T09:30:00Z')).toMatch(/2024/);
  });

  it.each(HOSTILE_VALUES)('falls back for %p', (value) => {
    expect(formatDateTime(value)).toBe(NOT_AVAILABLE);
  });
});

describe('formatRelative', () => {
  const now = new Date('2024-06-15T12:00:00Z');

  it('describes the past and future relative to `now`', () => {
    expect(formatRelative(new Date('2024-06-15T10:00:00Z'), NOT_AVAILABLE, now)).toMatch(/ago/);
    expect(formatRelative(new Date('2024-06-15T14:00:00Z'), NOT_AVAILABLE, now)).toMatch(/in /);
  });

  it('describes the present moment', () => {
    expect(formatRelative(now, NOT_AVAILABLE, now)).not.toBe(NOT_AVAILABLE);
  });

  it.each(HOSTILE_VALUES)('falls back for %p', (value) => {
    expect(formatRelative(value, NOT_AVAILABLE, now)).toBe(NOT_AVAILABLE);
  });

  it('falls back to the current clock when `now` itself is garbage', () => {
    expect(formatRelative(now, NOT_AVAILABLE, 'garbage')).not.toBe(NOT_AVAILABLE);
  });
});

describe('formatDuration', () => {
  it('formats hours and minutes', () => {
    expect(formatDuration(105)).toBe('1h 45m');
    expect(formatDuration(45)).toBe('45m');
    expect(formatDuration(120)).toBe('2h');
    expect(formatDuration(0)).toBe('0m');
  });

  it('supports a seconds unit', () => {
    expect(formatDuration(3600, { unit: 'seconds' })).toBe('1h');
  });

  it.each(HOSTILE_VALUES)('falls back for %p', (value) => {
    expect(formatDuration(value)).toBe(NOT_AVAILABLE);
  });

  it('falls back for a negative duration', () => {
    expect(formatDuration(-5)).toBe(NOT_AVAILABLE);
  });
});

describe('formatName', () => {
  it('prefers full_name', () => {
    expect(formatName({ full_name: 'Ada Lovelace', first_name: 'Ada' })).toBe('Ada Lovelace');
  });

  it('falls back to first + last name', () => {
    expect(formatName({ first_name: 'Ada', last_name: 'Lovelace' })).toBe('Ada Lovelace');
  });

  it('falls back to email when no name parts exist', () => {
    expect(formatName({ email: 'ada@example.com' })).toBe('ada@example.com');
  });

  it('falls back to the label when nothing usable is present', () => {
    expect(formatName(null)).toBe(UNKNOWN);
    expect(formatName(undefined)).toBe(UNKNOWN);
    expect(formatName({})).toBe(UNKNOWN);
    expect(formatName({ full_name: '   ' })).toBe(UNKNOWN);
  });

  it('accepts a custom label', () => {
    expect(formatName(null, NOT_ASSIGNED)).toBe(NOT_ASSIGNED);
  });
});

describe('formatCount', () => {
  it('pluralises correctly', () => {
    expect(formatCount(1, 'seat')).toBe('1 seat');
    expect(formatCount(4, 'seat')).toBe('4 seats');
    expect(formatCount(0, 'seat')).toBe('0 seats');
  });

  it('supports an irregular plural', () => {
    expect(formatCount(2, 'child', 'children')).toBe('2 children');
  });

  it.each(HOSTILE_VALUES)('falls back for %p', (value) => {
    expect(formatCount(value, 'seat')).toBe(NO_DATA);
  });

  it('falls back for a negative count', () => {
    expect(formatCount(-1, 'seat')).toBe(NO_DATA);
  });
});
