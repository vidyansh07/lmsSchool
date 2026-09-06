import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PendingActions, type PendingAction } from '@/components/pending-actions';

const items: PendingAction[] = [
  { id: '1', label: 'assignment', count: 12, href: '/teaching/assignments' },
  { id: '2', label: 'import', count: 0, href: '/admin/imports' },
];

describe('PendingActions', () => {
  it('renders a pluralised count and a review link', () => {
    render(<PendingActions items={items} />);
    expect(screen.getByText('12 assignments')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Review/ })).toHaveAttribute('href', '/teaching/assignments');
  });

  it('hides items with a zero count', () => {
    render(<PendingActions items={items} />);
    expect(screen.queryByText(/import/)).not.toBeInTheDocument();
  });

  it('shows a genuinely positive empty state when nothing is pending', () => {
    render(<PendingActions items={[{ id: '1', label: 'task', count: 0, href: '/x' }]} />);
    expect(screen.getByText('Nothing needs attention')).toBeInTheDocument();
    expect(screen.getByText('Your queue is clear.')).toBeInTheDocument();
  });

  it('marks an urgent item', () => {
    render(<PendingActions items={[{ id: '1', label: 'exam', count: 2, href: '/x', urgent: true }]} />);
    expect(screen.getByText('Urgent')).toBeInTheDocument();
  });

  it('shows a loading state', () => {
    render(<PendingActions items={[]} isLoading />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error state with retry', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<PendingActions items={[]} error={{ message: 'Could not load your queue.' }} onRetry={onRetry} />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('uses a custom action label when given one', () => {
    render(<PendingActions items={[{ id: '1', label: 'exam', count: 2, href: '/x', actionText: 'Grade' }]} />);
    expect(screen.getByRole('link', { name: /Grade/ })).toBeInTheDocument();
  });
});
