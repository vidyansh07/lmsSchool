import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { RecoveryKindList } from '@/components/recovery/kind-list';
import type { BinSummary } from '@/lib/recovery';

function kind(overrides: Partial<BinSummary> = {}): BinSummary {
  return { label: 'dsr.dsr', verbose_name: 'daily status reports', deleted_count: 3, ...overrides };
}

describe('RecoveryKindList', () => {
  it('shows a loading state before the kinds arrive', () => {
    render(<RecoveryKindList kinds={[]} isLoading error={null} onSelect={vi.fn()} />);
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
  });

  it('shows an error with retry on failure', () => {
    const onRetry = vi.fn();
    render(
      <RecoveryKindList
        kinds={[]}
        isLoading={false}
        error={{ message: 'Could not load the bin.', requestId: 'req-1' }}
        onRetry={onRetry}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('Could not load the bin.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('says the bin is empty when nothing has been deleted anywhere', () => {
    render(<RecoveryKindList kinds={[]} isLoading={false} error={null} onSelect={vi.fn()} />);
    expect(screen.getByText('The bin is empty')).toBeInTheDocument();
  });

  it('renders each kind with its verbose name and deleted count', () => {
    render(
      <RecoveryKindList
        kinds={[kind(), kind({ label: 'batches.batch', verbose_name: 'batches', deleted_count: 12 })]}
        isLoading={false}
        error={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('daily status reports')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('batches')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('selects a kind on row activation', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<RecoveryKindList kinds={[kind()]} isLoading={false} error={null} onSelect={onSelect} />);

    await user.click(screen.getByText('daily status reports'));
    expect(onSelect).toHaveBeenCalledWith(kind());
  });
});
