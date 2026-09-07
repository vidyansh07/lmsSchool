import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DeletedRecordsTable } from '@/components/recovery/deleted-records-table';
import { ApiError } from '@/lib/api';
import type { DeletedRecord } from '@/lib/recovery';
import type { Paginated } from '@/types/api';

const listDeletedRecords = vi.hoisted(() => vi.fn());
const restoreRecord = vi.hoisted(() => vi.fn());
vi.mock('@/lib/recovery', async () => {
  const actual = await vi.importActual<typeof import('@/lib/recovery')>('@/lib/recovery');
  return { ...actual, listDeletedRecords, restoreRecord };
});

const mockAuth = vi.hoisted(() => ({ value: { can: () => true } as { can: (capability: string) => boolean } }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => mockAuth.value }));

// PurgeControl is its own fully-tested component (recovery-purge-control.test.tsx);
// stubbing it here keeps this file's failures about the table, not about purge.
vi.mock('@/components/recovery/purge-control', () => ({
  PurgeControl: ({ record }: { record: DeletedRecord }) => <span data-testid="purge-stub">{record.id}</span>,
}));

function page(results: DeletedRecord[], overrides: Partial<Paginated<DeletedRecord>> = {}): Paginated<DeletedRecord> {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results, ...overrides };
}

function deletedRecord(overrides: Partial<DeletedRecord> = {}): DeletedRecord {
  return {
    id: 'batch-9',
    label: 'batches.batch',
    describes: 'GRS-B-009',
    deleted_at: '2026-09-01T12:00:00Z',
    deleted_by: 'admin@example.com',
    delete_reason: 'Duplicate entry.',
    ...overrides,
  };
}

beforeEach(() => {
  listDeletedRecords.mockReset();
  restoreRecord.mockReset();
  mockAuth.value = { can: () => true };
});

describe('DeletedRecordsTable states', () => {
  it('shows a loading state before the records arrive', () => {
    listDeletedRecords.mockReturnValue(new Promise(() => {}));
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
  });

  it('shows an error with retry when the records fail to load', async () => {
    listDeletedRecords.mockRejectedValueOnce(new ApiError(500, 'server_error', 'Could not load records.', 'req-1'));
    listDeletedRecords.mockResolvedValueOnce(page([deletedRecord()]));
    const user = userEvent.setup();
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Could not load records.')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(screen.getByText('GRS-B-009')).toBeInTheDocument());
  });

  it('says plainly when nothing of this kind is deleted', async () => {
    listDeletedRecords.mockResolvedValue(page([]));
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Nothing deleted of this kind')).toBeInTheDocument());
  });
});

describe('DeletedRecordsTable rendering and null handling', () => {
  it('renders what was deleted, when, by whom and why', async () => {
    listDeletedRecords.mockResolvedValue(page([deletedRecord()]));
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('GRS-B-009')).toBeInTheDocument());
    expect(screen.getByText('admin@example.com')).toBeInTheDocument();
    expect(screen.getByText('Duplicate entry.')).toBeInTheDocument();
    expect(screen.getByText(/2026/)).toBeInTheDocument();
  });

  it('renders "Unknown" rather than a blank when the deleting account has itself been removed', async () => {
    listDeletedRecords.mockResolvedValue(page([deletedRecord({ deleted_by: null })]));
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('GRS-B-009')).toBeInTheDocument());
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  it('renders "No data" rather than a blank for an unrecorded reason', async () => {
    listDeletedRecords.mockResolvedValue(page([deletedRecord({ delete_reason: '' })]));
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('GRS-B-009')).toBeInTheDocument());
    expect(screen.getByText('No data')).toBeInTheDocument();
  });

  it('renders a fallback rather than a blank for an empty description', async () => {
    listDeletedRecords.mockResolvedValue(page([deletedRecord({ describes: '' })]));
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('admin@example.com')).toBeInTheDocument());
    expect(screen.getByText('No data')).toBeInTheDocument();
  });
});

describe('DeletedRecordsTable restore', () => {
  it('hides the restore control without record.restore', async () => {
    mockAuth.value = { can: () => false };
    listDeletedRecords.mockResolvedValue(page([deletedRecord()]));
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('GRS-B-009')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /restore/i })).not.toBeInTheDocument();
  });

  it('restores a record, reloads the list and notifies the parent', async () => {
    listDeletedRecords.mockResolvedValueOnce(page([deletedRecord()]));
    listDeletedRecords.mockResolvedValueOnce(page([]));
    restoreRecord.mockResolvedValue(deletedRecord());
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<DeletedRecordsTable label="batches.batch" onChanged={onChanged} />);
    await waitFor(() => expect(screen.getByText('GRS-B-009')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /restore/i }));

    expect(restoreRecord).toHaveBeenCalledWith('batches.batch', 'batch-9');
    await waitFor(() => expect(screen.getByText('Nothing deleted of this kind')).toBeInTheDocument());
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it('shows an inline error and does not notify the parent when the restore fails', async () => {
    listDeletedRecords.mockResolvedValue(page([deletedRecord()]));
    restoreRecord.mockRejectedValue(new ApiError(409, 'conflict', 'That record is not deleted.', 'req-5'));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<DeletedRecordsTable label="batches.batch" onChanged={onChanged} />);
    await waitFor(() => expect(screen.getByText('GRS-B-009')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /restore/i }));

    await waitFor(() => expect(screen.getByText('That record is not deleted.')).toBeInTheDocument());
    expect(screen.getByText('GRS-B-009')).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe('DeletedRecordsTable pagination and purge wiring', () => {
  it('shows pagination once there is more than one page', async () => {
    listDeletedRecords.mockResolvedValue(
      page([deletedRecord()], { count: 45, total_pages: 3, page: 1, page_size: 20 }),
    );
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Showing 1–20 of 45')).toBeInTheDocument());
  });

  it('renders the purge control for each row', async () => {
    listDeletedRecords.mockResolvedValue(page([deletedRecord()]));
    render(<DeletedRecordsTable label="batches.batch" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByTestId('purge-stub')).toHaveTextContent('batch-9'));
  });
});
