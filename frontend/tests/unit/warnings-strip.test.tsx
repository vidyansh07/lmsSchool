/**
 * What needs doing: the rows, and the header button that opens them.
 *
 * These were a card on five dashboards. The card was tall, the figures people
 * came for sat underneath it, and the list is usually unchanged since
 * yesterday — so the rows moved into a panel behind one button that carries
 * the count. The rows themselves are untouched, and so are these assertions
 * about them.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WarningsButton } from '@/components/warnings-button';
import { WarningsList } from '@/components/warnings-strip';
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
    explanation: '',
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
    explanation: '',
    items: [],
  },
];

describe('the warning rows', () => {
  it('lists the warnings with counts and opens the names behind one', () => {
    render(<WarningsList warnings={warnings} />);
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
    render(<WarningsList warnings={[odd]} />);
    expect(screen.getByText('3 imported rows need a look')).toBeInTheDocument();
  });

  it('says so when nothing is waiting', () => {
    render(<WarningsList warnings={[]} />);
    expect(screen.getByText('Nothing is waiting on you.')).toBeInTheDocument();
  });
});

describe('the header button', () => {
  it('carries the count, so the card can go without the noticing going with it', () => {
    useApi.mockReturnValue({ data: warnings, error: null, isLoading: false, reload: vi.fn() });

    render(<WarningsButton />);

    expect(
      screen.getByRole('button', { name: /2 things, 1 today/ }),
    ).toBeInTheDocument();
  });

  it('is absent when nothing is waiting', () => {
    // A permanent zero is furniture: people stop seeing it, and then they stop
    // seeing it when it is not zero.
    useApi.mockReturnValue({ data: [], error: null, isLoading: false, reload: vi.fn() });

    const { container } = render(<WarningsButton />);

    expect(container).toBeEmptyDOMElement();
  });

  it('is absent for somebody the endpoint refuses', () => {
    // A student is refused `/warnings/` outright. The button does not check a
    // role; it has nothing to show, which is the same answer arrived at
    // without second-guessing the server.
    useApi.mockReturnValue({ data: null, error: null, isLoading: false, reload: vi.fn() });

    const { container } = render(<WarningsButton />);

    expect(container).toBeEmptyDOMElement();
  });

  it('opens the rows in a panel', () => {
    useApi.mockReturnValue({ data: warnings, error: null, isLoading: false, reload: vi.fn() });
    render(<WarningsButton />);

    fireEvent.click(screen.getByRole('button', { name: /2 things/ }));

    expect(screen.getByRole('heading', { name: 'Needs attention' })).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /past the date a payment was expected/ }),
    ).toBeInTheDocument();
  });

  it('still offers the full page from the panel', () => {
    useApi.mockReturnValue({ data: warnings, error: null, isLoading: false, reload: vi.fn() });
    render(<WarningsButton />);

    fireEvent.click(screen.getByRole('button', { name: /2 things/ }));

    expect(screen.getByRole('link', { name: /See all/ })).toHaveAttribute(
      'href',
      '/needs-attention',
    );
  });

  it('stays visible when the check itself failed', () => {
    // An error is a thing somebody should know about, not a reason to hide
    // the only way to find out.
    useApi.mockReturnValue({
      data: null,
      error: { message: 'Service unavailable', requestId: 'abc' },
      isLoading: false,
      reload: vi.fn(),
    });

    render(<WarningsButton />);

    expect(screen.getByRole('button', { name: /could not check/i })).toBeInTheDocument();
  });
});
