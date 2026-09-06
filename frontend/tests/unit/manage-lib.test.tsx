import { describe, expect, it } from 'vitest';

import { describeRiskFlag, describeTimelineVariance } from '@/lib/manage';

describe('describeTimelineVariance', () => {
  it('says a batch has not started, regardless of the variance figure', () => {
    expect(describeTimelineVariance('not_started', null)).toBe('This batch has not started yet.');
    expect(describeTimelineVariance('not_started', 12)).toBe('This batch has not started yet.');
  });

  it('says there is not enough data when the variance is null and the batch has started', () => {
    expect(describeTimelineVariance('on_track', null)).toBe(
      'Not enough of the course has run yet to compare plan against actual.',
    );
    expect(describeTimelineVariance('behind', null)).toBe(
      'Not enough of the course has run yet to compare plan against actual.',
    );
  });

  it('states a behind-schedule batch in words, with the correct singular/plural', () => {
    expect(describeTimelineVariance('behind', -8)).toBe('8 percentage points behind the plan.');
    expect(describeTimelineVariance('behind', -1)).toBe('1 percentage point behind the plan.');
  });

  it('states an ahead-of-schedule batch in words', () => {
    expect(describeTimelineVariance('ahead', 5)).toBe('5 percentage points ahead of the plan.');
  });

  it('describes on-track without a number, since on-track needs no magnitude', () => {
    expect(describeTimelineVariance('on_track', 0)).toBe('Running on track with the plan.');
  });

  it('rounds a fractional variance to a whole number of points', () => {
    expect(describeTimelineVariance('behind', -4.6)).toBe('5 percentage points behind the plan.');
  });
});

describe('describeRiskFlag', () => {
  it('uses the risk engine’s own labels for known flag keys', () => {
    expect(describeRiskFlag('attendance')).toBe('Attendance');
    expect(describeRiskFlag('academic')).toBe('Assessment average');
    expect(describeRiskFlag('assignments')).toBe('Missed assignments');
    expect(describeRiskFlag('progress')).toBe('Course progress');
  });

  it('humanises an unrecognised flag rather than hiding it', () => {
    expect(describeRiskFlag('fee_overdue')).toBe('Fee overdue');
    expect(describeRiskFlag('low-engagement')).toBe('Low engagement');
  });

  it('never renders a blank for a degenerate flag string', () => {
    expect(describeRiskFlag('')).toBe('Risk flag');
    expect(describeRiskFlag('___')).toBe('Risk flag');
  });

  it('capitalises only the first letter of a humanised flag', () => {
    expect(describeRiskFlag('needs_manager_review')).toBe('Needs manager review');
  });
});
