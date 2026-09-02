import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { EmptyState, ErrorState, LoadingState } from '@/components/states';

describe('LoadingState', () => {
  it('announces itself to assistive technology', () => {
    render(<LoadingState label="Loading users…" />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('Loading users…')).toBeInTheDocument();
  });
});

describe('ErrorState', () => {
  it('shows the message, the reference id and a retry action', async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Could not reach the server." requestId="req-42" onRetry={onRetry} />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Could not reach the server.')).toBeInTheDocument();
    expect(screen.getByText('req-42')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('omits the retry action when no handler is given', () => {
    render(<ErrorState message="Broken." />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('EmptyState', () => {
  it('renders a title and description', () => {
    render(<EmptyState title="No courses yet" description="Create one to get started." />);
    expect(screen.getByText('No courses yet')).toBeInTheDocument();
    expect(screen.getByText('Create one to get started.')).toBeInTheDocument();
  });
});
