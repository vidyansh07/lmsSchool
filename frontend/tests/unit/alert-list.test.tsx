import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AlertList, type AlertItem } from '@/components/alert-list';

const items: AlertItem[] = [
  { id: '1', severity: 'error', title: 'Payment failed', description: '3 students', count: 3, href: '/admin/fees' },
  { id: '2', severity: 'warning', title: 'Batch has no trainer', href: '/admin/batches/2' },
];

describe('AlertList', () => {
  it('renders each alert with its severity and count', () => {
    render(<AlertList items={items} />);
    expect(screen.getByText('Payment failed')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Batch has no trainer')).toBeInTheDocument();
  });

  it('links an alert that has an href', () => {
    render(<AlertList items={items} />);
    expect(screen.getByRole('link', { name: /Payment failed/ })).toHaveAttribute('href', '/admin/fees');
  });

  it('shows a positive, specific empty state rather than a generic empty box', () => {
    render(<AlertList items={[]} emptyTitle="Nothing needs attention" emptyDescription="All clear." />);
    expect(screen.getByText('Nothing needs attention')).toBeInTheDocument();
    expect(screen.getByText('All clear.')).toBeInTheDocument();
  });

  it('shows a loading state', () => {
    render(<AlertList items={[]} isLoading title="fee alerts" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error state with retry', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<AlertList items={[]} error={{ message: 'Could not load alerts.' }} onRetry={onRetry} />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('falls back to a placeholder title rather than rendering nothing', () => {
    render(<AlertList items={[{ id: '1', severity: 'info', title: '' }]} />);
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });
});
