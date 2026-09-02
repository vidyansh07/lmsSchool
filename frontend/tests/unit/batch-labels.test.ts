import { describe, expect, it } from 'vitest';

import {
  BATCH_STATUS_LABEL,
  ENROLLMENT_STATUS_LABEL,
  WEEKDAY_LABEL,
  formatTime,
  isoDaysFromNow,
  isoToday,
} from '@/lib/batch-labels';

describe('formatTime', () => {
  it('trims the API seconds', () => {
    expect(formatTime('09:00:00')).toBe('09:00');
    expect(formatTime('18:30:00')).toBe('18:30');
  });

  it('handles a missing value', () => {
    expect(formatTime(null)).toBe('');
  });
});

describe('weekday labels', () => {
  it('starts at Monday, matching the API', () => {
    expect(WEEKDAY_LABEL[0]).toBe('Monday');
    expect(WEEKDAY_LABEL[6]).toBe('Sunday');
  });
});

describe('status labels', () => {
  it('covers every batch and enrolment status', () => {
    expect(Object.keys(BATCH_STATUS_LABEL)).toEqual([
      'upcoming',
      'active',
      'completed',
      'cancelled',
      'archived',
    ]);
    expect(Object.keys(ENROLLMENT_STATUS_LABEL)).toEqual([
      'pending',
      'active',
      'suspended',
      'completed',
      'cancelled',
    ]);
  });
});

describe('iso helpers', () => {
  it('produce plain day strings', () => {
    expect(isoToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(isoDaysFromNow(7)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(isoDaysFromNow(7) > isoToday()).toBe(true);
  });
});
