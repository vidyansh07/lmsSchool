import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PresentNowStrip } from '@/components/academics/present-now';

const getPresentNow = vi.hoisted(() => vi.fn());
vi.mock('@/lib/academics', () => ({ getPresentNow }));

describe('PresentNowStrip', () => {
  it('shows online, in person and total present, and how many registers are in', async () => {
    getPresentNow.mockResolvedValue({
      date: '2026-10-07',
      online: 14,
      offline: 31,
      total: 45,
      absent: 6,
      sessions_today: 5,
      registers_taken: 4,
    });
    render(<PresentNowStrip />);
    const strip = await screen.findByTestId('present-now');
    expect(strip).toHaveTextContent('Present online');
    expect(strip).toHaveTextContent('14');
    expect(strip).toHaveTextContent('Present in person');
    expect(strip).toHaveTextContent('31');
    expect(strip).toHaveTextContent('Present today');
    expect(strip).toHaveTextContent('45');
    expect(strip).toHaveTextContent('4 of 5 classes');
  });

  it('says so when the count cannot be read, instead of showing zeros', async () => {
    getPresentNow.mockRejectedValue(new Error('offline'));
    render(<PresentNowStrip />);
    expect(await screen.findByTestId('present-now-error')).toHaveTextContent(/Present today:/);
  });
});
