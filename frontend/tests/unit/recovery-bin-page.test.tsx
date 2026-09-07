import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RecoveryBin } from '@/app/admin/recovery/page';
import { ApiError } from '@/lib/api';
import type { BinSummary } from '@/lib/recovery';

const listRecoveryKinds = vi.hoisted(() => vi.fn());
vi.mock('@/lib/recovery', async () => {
  const actual = await vi.importActual<typeof import('@/lib/recovery')>('@/lib/recovery');
  return { ...actual, listRecoveryKinds };
});

// DeletedRecordsTable is fully tested on its own
// (recovery-deleted-records-table.test.tsx); this stub isolates RecoveryBin's
// own job — picking a kind, showing it, wiring `onChanged` back to a reload —
// from that table's internals.
vi.mock('@/components/recovery/deleted-records-table', () => ({
  DeletedRecordsTable: ({ label, onChanged }: { label: string; onChanged: () => void }) => (
    <div data-testid="deleted-records-table-stub">
      <span>{label}</span>
      <button type="button" onClick={onChanged}>
        simulate a change
      </button>
    </div>
  ),
}));

function kind(overrides: Partial<BinSummary> = {}): BinSummary {
  return { label: 'dsr.dsr', verbose_name: 'daily status reports', deleted_count: 3, ...overrides };
}

beforeEach(() => {
  listRecoveryKinds.mockReset();
});

describe('RecoveryBin landing view', () => {
  it('shows a loading state before the kinds arrive', () => {
    listRecoveryKinds.mockReturnValue(new Promise(() => {}));
    render(<RecoveryBin />);
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
  });

  it('shows an error with retry when the kinds fail to load', async () => {
    listRecoveryKinds.mockRejectedValueOnce(new ApiError(500, 'server_error', 'Could not load the bin.', 'req-1'));
    listRecoveryKinds.mockResolvedValueOnce([kind()]);
    const user = userEvent.setup();
    render(<RecoveryBin />);

    await waitFor(() => expect(screen.getByText('Could not load the bin.')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(screen.getByText('daily status reports')).toBeInTheDocument());
  });

  it('lists every kind currently holding a deletion', async () => {
    listRecoveryKinds.mockResolvedValue([kind(), kind({ label: 'batches.batch', verbose_name: 'batches', deleted_count: 1 })]);
    render(<RecoveryBin />);
    await waitFor(() => expect(screen.getByText('daily status reports')).toBeInTheDocument());
    expect(screen.getByText('batches')).toBeInTheDocument();
  });
});

describe('RecoveryBin drill-down', () => {
  it('shows a kind’s deleted records on selection, and names the kind', async () => {
    listRecoveryKinds.mockResolvedValue([kind()]);
    const user = userEvent.setup();
    render(<RecoveryBin />);
    await waitFor(() => expect(screen.getByText('daily status reports')).toBeInTheDocument());

    await user.click(screen.getByText('daily status reports'));
    expect(screen.getByTestId('deleted-records-table-stub')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'daily status reports' })).toBeInTheDocument();
  });

  it('states the deleted count in words, singular and plural', async () => {
    listRecoveryKinds.mockResolvedValue([kind({ deleted_count: 1 }), kind({ label: 'x', verbose_name: 'x things', deleted_count: 4 })]);
    const user = userEvent.setup();
    render(<RecoveryBin />);
    await waitFor(() => expect(screen.getByText('daily status reports')).toBeInTheDocument());

    await user.click(screen.getByText('daily status reports'));
    expect(screen.getByText('1 deleted record.', { exact: false })).toBeInTheDocument();
  });

  it('returns to the kind list from the back link, without a route change', async () => {
    listRecoveryKinds.mockResolvedValue([kind()]);
    const user = userEvent.setup();
    render(<RecoveryBin />);
    await waitFor(() => expect(screen.getByText('daily status reports')).toBeInTheDocument());
    await user.click(screen.getByText('daily status reports'));
    expect(screen.getByTestId('deleted-records-table-stub')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /all kinds/i }));
    expect(screen.queryByTestId('deleted-records-table-stub')).not.toBeInTheDocument();
    expect(screen.getByText('daily status reports')).toBeInTheDocument();
  });

  it('reloads the kind counts when the drill-down reports a change', async () => {
    listRecoveryKinds.mockResolvedValue([kind()]);
    const user = userEvent.setup();
    render(<RecoveryBin />);
    await waitFor(() => expect(screen.getByText('daily status reports')).toBeInTheDocument());
    await user.click(screen.getByText('daily status reports'));
    await waitFor(() => expect(listRecoveryKinds).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole('button', { name: /simulate a change/i }));
    await waitFor(() => expect(listRecoveryKinds).toHaveBeenCalledTimes(2));
  });
});
