import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import NeedsAttentionPage from '@/app/needs-attention/page';
import type { StaffWarning } from '@/types/api';

/**
 * The page somebody works their list from, as opposed to the card they glance
 * at. What it must get right is grouping and completeness: a warning that
 * exists and is not shown is worse than one shown under the wrong heading.
 */
const api = vi.hoisted(() => ({
  data: null as StaffWarning[] | null,
  error: null as { message: string; requestId: string } | null,
  isLoading: false,
}));

vi.mock('@/hooks/use-api', () => ({
  useApi: () => ({ ...api, reload: vi.fn() }),
}));

vi.mock('@/components/require-auth', () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

function warning(overrides: Partial<StaffWarning>): StaffWarning {
  return {
    kind: 'fees_overdue',
    severity: 'error',
    label: '3 fees overdue',
    count: 3,
    href: '/fees',
    explanation: 'Money is still owed.',
    items: [{ label: 'Asha Rao', href: '/admissions/1' }],
    ...overrides,
  };
}

describe('the needs-attention page', () => {
  beforeEach(() => {
    api.data = null;
    api.error = null;
    api.isLoading = false;
  });

  it('groups by how soon a thing matters', () => {
    api.data = [
      warning({ kind: 'a', severity: 'error', label: 'Today thing' }),
      warning({ kind: 'b', severity: 'warning', label: 'Week thing' }),
      warning({ kind: 'c', severity: 'info', label: 'Loose end' }),
    ];

    render(<NeedsAttentionPage />);

    expect(screen.getByRole('heading', { name: 'Today' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'This week' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Worth knowing' })).toBeInTheDocument();
  });

  it('leaves out a group with nothing in it', () => {
    api.data = [warning({ severity: 'error' })];

    render(<NeedsAttentionPage />);

    expect(screen.queryByRole('heading', { name: 'This week' })).not.toBeInTheDocument();
  });

  it('says what a warning means, not only what it is', () => {
    // The whole reason this is a page: "12 batches overrun" tells somebody who
    // already knows the system what to do, and a new administrator nothing.
    api.data = [warning({ explanation: 'These classes are past their end date.' })];

    render(<NeedsAttentionPage />);

    expect(screen.getByText('These classes are past their end date.')).toBeInTheDocument();
  });

  it('shows the names without an expand step', () => {
    api.data = [warning({ items: [{ label: 'Asha Rao', href: '/admissions/1' }] })];

    render(<NeedsAttentionPage />);

    expect(screen.getByRole('link', { name: 'Asha Rao' })).toBeInTheDocument();
  });

  it('says plainly when there are more than it lists', () => {
    // The server sends at most five. Counting names against the badge and
    // coming up short should not be a puzzle.
    api.data = [
      warning({ count: 12, items: [{ label: 'Asha Rao', href: '/admissions/1' }] }),
    ];

    render(<NeedsAttentionPage />);

    expect(screen.getByText('and 11 more')).toBeInTheDocument();
  });

  it('offers the way to fix it', () => {
    api.data = [warning({ href: '/fees' })];

    render(<NeedsAttentionPage />);

    expect(screen.getByRole('link', { name: /Go and fix this/ })).toHaveAttribute('href', '/fees');
  });

  it('still shows a warning whose severity it does not recognise', () => {
    // A kind added later must not vanish from the one page that lists
    // everything.
    api.data = [
      warning({ kind: 'novel', severity: 'critical' as StaffWarning['severity'], label: 'Novel' }),
    ];

    render(<NeedsAttentionPage />);

    expect(screen.getByText('Novel')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Other' })).toBeInTheDocument();
  });

  it('says so when nothing is waiting', () => {
    api.data = [];

    render(<NeedsAttentionPage />);

    expect(screen.getByText('Nothing is waiting on you.')).toBeInTheDocument();
  });

  it('offers a retry when the check itself failed', () => {
    api.error = { message: 'Service unavailable', requestId: 'abc' };

    render(<NeedsAttentionPage />);

    expect(screen.getByText('Could not check')).toBeInTheDocument();
  });
});
