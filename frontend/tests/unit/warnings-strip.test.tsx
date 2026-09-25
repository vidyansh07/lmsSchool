/**
 * The warnings strip: server-computed lines with a count and a link, the
 * names behind a number on demand, and a calm state when nothing is waiting.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WarningsStrip } from '@/components/warnings-strip';
import type { StaffWarning } from '@/types/api';

const useApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi }));

const warnings: StaffWarning[] = [
  {
    kind: 'fees_overdue',
    severity: 'error',
    label: '2 students past the date a payment was expected',
    count: 2,
    href: '/admin/students?fee_status=overdue',
    items: [
      { label: 'Rahul Verma · ₹9,000 owed since 10 Sep', href: '/admissions/s1' },
      { label: 'Asha Rao · ₹4,000 owed since 12 Sep', href: '/admissions/s2' },
    ],
  },
  {
    kind: 'email_unverified',
    severity: 'info',
    label: '1 staff account never verified their email',
    count: 1,
    href: '/admin/users',
    items: [],
  },
];

describe('WarningsStrip', () => {
  it('lists the warnings with counts and opens the names behind one', () => {
    useApi.mockReturnValue({ data: warnings, error: null, isLoading: false, reload: vi.fn() });
    render(<WarningsStrip />);
    expect(screen.getByText('2 things to look at, 1 today.')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /past the date a payment was expected/ }),
    ).toHaveAttribute('href', '/admin/students?fee_status=overdue');
    fireEvent.click(screen.getByRole('button', { name: /Show 2 of 2/ }));
    expect(screen.getByRole('link', { name: /Rahul Verma/ })).toHaveAttribute(
      'href',
      '/admissions/s1',
    );
  });

  it('renders a warning whose severity it does not know, on the informational tone, rather than throwing', () => {
    // One bad row must not take down the five dashboards that mount the strip.
    const odd: StaffWarning = {
      ...warnings[1]!,
      kind: 'imported_oddity',
      severity: 'urgent' as StaffWarning['severity'],
      label: '3 imported rows need a look',
    };
    useApi.mockReturnValue({ data: [odd], error: null, isLoading: false, reload: vi.fn() });
    render(<WarningsStrip />);
    expect(screen.getByText('3 imported rows need a look')).toBeInTheDocument();
  });

  it('says so when nothing is waiting', () => {
    useApi.mockReturnValue({ data: [], error: null, isLoading: false, reload: vi.fn() });
    render(<WarningsStrip />);
    expect(screen.getByText('Nothing is waiting on you.')).toBeInTheDocument();
  });
});
