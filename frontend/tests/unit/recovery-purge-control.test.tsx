import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PurgeControl } from '@/components/recovery/purge-control';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import type { DeletedRecord } from '@/lib/recovery';

const purgeRecord = vi.hoisted(() => vi.fn());
vi.mock('@/lib/recovery', async () => {
  const actual = await vi.importActual<typeof import('@/lib/recovery')>('@/lib/recovery');
  return { ...actual, purgeRecord };
});

const mockAuth = vi.hoisted(() => ({ value: { can: () => true } as { can: (capability: string) => boolean } }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => mockAuth.value }));

function record(overrides: Partial<DeletedRecord> = {}): DeletedRecord {
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
  purgeRecord.mockReset();
  mockAuth.value = { can: () => true };
});

describe('PurgeControl authorization', () => {
  it('does not render at all without record.purge', () => {
    mockAuth.value = { can: () => false };
    render(<PurgeControl record={record()} onPurged={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /purge/i })).not.toBeInTheDocument();
  });

  it('checks the record.purge capability specifically', () => {
    const can = vi.fn(() => true);
    mockAuth.value = { can };
    render(<PurgeControl record={record()} onPurged={vi.fn()} />);
    expect(can).toHaveBeenCalledWith(Capability.recordPurge);
  });

  it('shows the purge trigger for someone holding record.purge', () => {
    render(<PurgeControl record={record()} onPurged={vi.fn()} />);
    expect(screen.getByRole('button', { name: /purge/i })).toBeInTheDocument();
  });
});

describe('PurgeControl reason gate', () => {
  it('opens a reason field without calling the API', async () => {
    const user = userEvent.setup();
    render(<PurgeControl record={record()} onPurged={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: /purge/i }));
    expect(screen.getByLabelText(/why destroy this permanently/i)).toBeInTheDocument();
    expect(purgeRecord).not.toHaveBeenCalled();
  });

  it('keeps the destroy button disabled until a reason is typed', async () => {
    const user = userEvent.setup();
    render(<PurgeControl record={record()} onPurged={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /purge/i }));

    expect(screen.getByRole('button', { name: /destroy permanently/i })).toBeDisabled();
    await user.type(screen.getByLabelText(/why destroy this permanently/i), 'No longer needed.');
    expect(screen.getByRole('button', { name: /destroy permanently/i })).toBeEnabled();
  });

  it('cancelling the reason panel collapses back to the trigger and forgets the reason', async () => {
    const user = userEvent.setup();
    render(<PurgeControl record={record()} onPurged={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /purge/i }));
    await user.type(screen.getByLabelText(/why destroy this permanently/i), 'No longer needed.');

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByLabelText(/why destroy this permanently/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /purge/i }));
    expect(screen.getByLabelText(/why destroy this permanently/i)).toHaveValue('');
  });
});

describe('PurgeControl confirmation', () => {
  it('does not call the API on the first destroy click — it opens the confirm dialog', async () => {
    const user = userEvent.setup();
    render(<PurgeControl record={record()} onPurged={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /purge/i }));
    await user.type(screen.getByLabelText(/why destroy this permanently/i), 'No longer needed.');

    await user.click(screen.getByRole('button', { name: /destroy permanently/i }));
    expect(purgeRecord).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  });

  it('names what is being destroyed in the confirm dialog', async () => {
    const user = userEvent.setup();
    render(<PurgeControl record={record({ describes: 'GRS-B-009' })} onPurged={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /purge/i }));
    await user.type(screen.getByLabelText(/why destroy this permanently/i), 'No longer needed.');
    await user.click(screen.getByRole('button', { name: /destroy permanently/i }));

    expect(screen.getByRole('alertdialog')).toHaveAccessibleDescription(/GRS-B-009/);
  });

  it('calls purgeRecord with the typed reason once confirmed, and reports success', async () => {
    purgeRecord.mockResolvedValue(undefined);
    const onPurged = vi.fn();
    const user = userEvent.setup();
    render(<PurgeControl record={record({ label: 'batches.batch', id: 'batch-9' })} onPurged={onPurged} />);

    await user.click(screen.getByRole('button', { name: /purge/i }));
    await user.type(screen.getByLabelText(/why destroy this permanently/i), 'No longer needed.');
    await user.click(screen.getByRole('button', { name: /destroy permanently/i }));

    const dialog = screen.getByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: /destroy permanently/i }));

    expect(purgeRecord).toHaveBeenCalledWith('batches.batch', 'batch-9', 'No longer needed.');
    await waitFor(() => expect(onPurged).toHaveBeenCalledOnce());
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('cancelling the dialog does not call the API and leaves the reason in place', async () => {
    const user = userEvent.setup();
    render(<PurgeControl record={record()} onPurged={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /purge/i }));
    await user.type(screen.getByLabelText(/why destroy this permanently/i), 'No longer needed.');
    await user.click(screen.getByRole('button', { name: /destroy permanently/i }));

    await user.keyboard('{Escape}');
    expect(purgeRecord).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/why destroy this permanently/i)).toHaveValue('No longer needed.');
  });

  it('shows an inline error and does not report success when the purge fails', async () => {
    purgeRecord.mockRejectedValue(new ApiError(409, 'conflict', 'Only a deleted record can be destroyed.', 'req-4'));
    const onPurged = vi.fn();
    const user = userEvent.setup();
    render(<PurgeControl record={record()} onPurged={onPurged} />);

    await user.click(screen.getByRole('button', { name: /purge/i }));
    await user.type(screen.getByLabelText(/why destroy this permanently/i), 'No longer needed.');
    await user.click(screen.getByRole('button', { name: /destroy permanently/i }));
    const dialog = screen.getByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: /destroy permanently/i }));

    await waitFor(() => expect(screen.getByText('Only a deleted record can be destroyed.')).toBeInTheDocument());
    expect(onPurged).not.toHaveBeenCalled();
    // `Confirm` now plays the same fade/scale exit `components/ui/dialog.tsx`
    // uses, staying mounted for the exit animation's duration — see
    // `tests/unit/ui-dialog.test.tsx`'s identical wait for the same reason.
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });
});
