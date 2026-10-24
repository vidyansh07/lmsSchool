/**
 * The instalment editor's arithmetic: whether a schedule adds up, and what
 * the schedule being typed would mean for a student who has already paid
 * something.
 */
import { describe, expect, it } from 'vitest';

import { coverageOf, installmentsAddUp } from '@/components/fees/installment-editor';
import type { InstallmentInput } from '@/types/api';

describe('installmentsAddUp', () => {
  it('is true for no schedule at all, which means ad hoc', () => {
    expect(installmentsAddUp([], 10000)).toBe(true);
  });

  it('refuses a row with no date or no amount', () => {
    expect(installmentsAddUp([{ amount: '10000', due_on: '' }], 10000)).toBe(false);
    expect(installmentsAddUp([{ amount: '0', due_on: '2026-11-01' }], 10000)).toBe(false);
  });

  it('holds to the paisa', () => {
    const rows: InstallmentInput[] = [
      { amount: '3333.34', due_on: '2026-11-01' },
      { amount: '3333.33', due_on: '2026-12-01' },
      { amount: '3333.33', due_on: '2027-01-01' },
    ];
    expect(installmentsAddUp(rows, 10000)).toBe(true);
    expect(installmentsAddUp(rows, 10000.01)).toBe(false);
  });
});

describe('coverageOf', () => {
  it('covers instalments in order with what has been received', () => {
    const rows: InstallmentInput[] = [
      { amount: '5000', due_on: '2026-11-01' },
      { amount: '5000', due_on: '2026-12-01' },
      { amount: '5000', due_on: '2027-01-01' },
    ];
    // The ledger's own rule: the first is settled, the second partly, the
    // rest pending.
    expect(coverageOf(rows, 7000)).toEqual(['paid', 'part', 'pending']);
  });

  it('calls nothing paid when nothing has been received', () => {
    expect(coverageOf([{ amount: '100', due_on: '2026-11-01' }], 0)).toEqual(['pending']);
  });

  it('settles every instalment once the whole fee is in', () => {
    const rows: InstallmentInput[] = [
      { amount: '100', due_on: '2026-11-01' },
      { amount: '100', due_on: '2026-12-01' },
    ];
    expect(coverageOf(rows, 200)).toEqual(['paid', 'paid']);
  });
});
