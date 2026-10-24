/**
 * Import Students: preview, then import.
 *
 * The first step is not optional, and that is the behaviour worth pinning —
 * an importer that wrote first and reported afterwards would be a
 * spreadsheet typo turned into thirty student records.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ImportSheetDialog } from '@/components/batches/import-sheet-dialog';
import { ApiError } from '@/lib/api';
import type { BatchSheetImportResult } from '@/lib/batches';

const importBatchSheet = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, importBatchSheet };
});

function result(overrides: Partial<BatchSheetImportResult> = {}): BatchSheetImportResult {
  return {
    batches_created: 2,
    batches_matched: 0,
    students_created: 31,
    students_matched: 1,
    enrolments_created: 32,
    enrolments_existing: 0,
    batches: ['GRS-B-0007 10:00 AM · Nov 2026'],
    problems: [],
    ...overrides,
  };
}

function choose() {
  const file = new File(['x'], 'batches.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  fireEvent.change(screen.getByLabelText(/Batch sheet/), { target: { files: [file] } });
  return file;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ImportSheetDialog', () => {
  it('will not import before it has previewed', () => {
    render(<ImportSheetDialog open onClose={vi.fn()} onImported={vi.fn()} />);
    choose();

    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Preview/ })).toBeEnabled();
  });

  it('previews as a dry run and shows what it would do', async () => {
    importBatchSheet.mockResolvedValue(result());
    render(<ImportSheetDialog open onClose={vi.fn()} onImported={vi.fn()} />);
    choose();

    fireEvent.click(screen.getByRole('button', { name: /Preview/ }));
    await waitFor(() =>
      expect(importBatchSheet).toHaveBeenCalledWith(expect.any(File), { dryRun: true }),
    );
    expect(await screen.findByText('31')).toBeInTheDocument();
    expect(screen.getByText('Every row in the file can be used.')).toBeInTheDocument();
  });

  it('lists the rows it could not use, with the sheet and the row', async () => {
    importBatchSheet.mockResolvedValue(
      result({
        problems: [
          { sheet: 'Batches', row: 12, message: 'A roster row with no name; nothing to create.' },
        ],
      }),
    );
    render(<ImportSheetDialog open onClose={vi.fn()} onImported={vi.fn()} />);
    choose();

    fireEvent.click(screen.getByRole('button', { name: /Preview/ }));
    expect(await screen.findByText('Batches')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText(/no name/)).toBeInTheDocument();
  });

  it('imports for real once previewed, and says what it did', async () => {
    const onImported = vi.fn();
    importBatchSheet.mockResolvedValue(result());
    render(<ImportSheetDialog open onClose={vi.fn()} onImported={onImported} />);
    choose();

    fireEvent.click(screen.getByRole('button', { name: /Preview/ }));
    await screen.findByText('31');
    fireEvent.click(screen.getByRole('button', { name: 'Import' }));

    await waitFor(() =>
      expect(importBatchSheet).toHaveBeenLastCalledWith(expect.any(File), { dryRun: false }),
    );
    await waitFor(() =>
      expect(onImported).toHaveBeenCalledWith(
        '2 batch(es) opened, 31 student(s) added, 32 enrolled.',
      ),
    );
  });

  it('asks for a file rather than posting nothing', async () => {
    render(<ImportSheetDialog open onClose={vi.fn()} onImported={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /Preview/ }));
    // The button is disabled with no file, so nothing is sent either way.
    expect(importBatchSheet).not.toHaveBeenCalled();
  });

  it('says what went wrong when the file cannot be read', async () => {
    importBatchSheet.mockRejectedValue(
      new ApiError(400, 'validation_error', 'This file could not be read as a spreadsheet (.xlsx).', 'r1'),
    );
    render(<ImportSheetDialog open onClose={vi.fn()} onImported={vi.fn()} />);
    choose();

    fireEvent.click(screen.getByRole('button', { name: /Preview/ }));
    expect(
      await screen.findByText('This file could not be read as a spreadsheet (.xlsx).'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();
  });
});
