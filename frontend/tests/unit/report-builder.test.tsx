/**
 * Building a report: pick a thing, choose what to show, ask it questions.
 *
 * Everything the screen offers comes from the server's description of each
 * dataset — its columns, the questions each field will answer, what it will
 * total. So what is pinned here is that the screen stays a renderer of that
 * description rather than a second copy of it: the operators offered are the
 * ones the field declares and no others, the control matches the field's
 * kind, and changing dataset starts afresh rather than carrying selections
 * the next dataset has never heard of.
 *
 * And the two things a result has to be honest about: that it was cut, and
 * that a grouped answer is a different shape from a list.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ReportBuilder } from '@/app/admin/reports/build/page';
import { ApiError } from '@/lib/api';
import type { ReportDataset } from '@/types/api';

const listDatasets = vi.hoisted(() => vi.fn());
const buildReport = vi.hoisted(() => vi.fn());
vi.mock('@/lib/reporting', async () => {
  const actual = await vi.importActual<typeof import('@/lib/reporting')>('@/lib/reporting');
  return { ...actual, listDatasets, buildReport };
});

const PAYMENTS: ReportDataset = {
  key: 'fee_payments',
  label: 'Fee payments',
  description: 'Every receipt.',
  columns: [
    { name: 'receipt', label: 'Receipt' },
    { name: 'course', label: 'Course' },
    { name: 'amount', label: 'Amount' },
  ],
  filters: [
    {
      name: 'paid_on',
      label: 'Paid on',
      kind: 'date',
      operators: [
        { value: 'gte', label: 'on or after' },
        { value: 'lte', label: 'on or before' },
      ],
      choices: null,
    },
    {
      name: 'method',
      label: 'Method',
      kind: 'choice',
      operators: [{ value: 'exact', label: 'is' }],
      choices: [
        { value: 'cash', label: 'Cash' },
        { value: 'upi', label: 'UPI' },
      ],
    },
  ],
  measures: [
    { name: 'count', label: 'Receipts', kind: 'count' },
    { name: 'total', label: 'Collected', kind: 'sum' },
  ],
};

const STUDENTS: ReportDataset = {
  key: 'students',
  label: 'Students',
  description: 'Everybody on the roll.',
  columns: [{ name: 'student_id', label: 'Student ID' }],
  filters: [
    {
      name: 'city',
      label: 'City',
      kind: 'text',
      operators: [{ value: 'icontains', label: 'contains' }],
      choices: null,
    },
  ],
  measures: [{ name: 'count', label: 'Students', kind: 'count' }],
};

beforeEach(() => {
  vi.clearAllMocks();
  listDatasets.mockResolvedValue([PAYMENTS, STUDENTS]);
  buildReport.mockResolvedValue({
    columns: [{ name: 'receipt', label: 'Receipt' }],
    rows: [{ receipt: 'GRS-R-00001' }],
    truncated: false,
    grouped: false,
  });
});

async function choose(dataset: string) {
  await screen.findByRole('option', { name: 'Fee payments' });
  fireEvent.change(screen.getByLabelText('Report on'), { target: { value: dataset } });
}

describe('ReportBuilder', () => {
  it('offers only the questions a field declares', async () => {
    render(<ReportBuilder />);
    await choose('fee_payments');

    fireEvent.change(screen.getByLabelText('Ask about'), { target: { value: 'paid_on' } });

    const operators = await screen.findByLabelText('Question');
    // `gte` and `lte` are what a date offers. Nothing else is on the list,
    // which is the same allowlist the server enforces — the screen simply
    // never offers what would be refused.
    expect(
      Array.from(operators.querySelectorAll('option')).map((option) => option.textContent),
    ).toEqual(['on or after', 'on or before']);
  });

  it('gives a choice field its own choices rather than a free-text box', async () => {
    render(<ReportBuilder />);
    await choose('fee_payments');

    fireEvent.change(screen.getByLabelText('Ask about'), { target: { value: 'method' } });

    const value = await screen.findByLabelText('Value');
    expect(Array.from(value.querySelectorAll('option')).map((o) => o.textContent)).toContain(
      'Cash',
    );
  });

  it('sends what was asked, with the dataset and the clause', async () => {
    render(<ReportBuilder />);
    await choose('fee_payments');

    fireEvent.change(screen.getByLabelText('Ask about'), { target: { value: 'method' } });
    fireEvent.change(await screen.findByLabelText('Value'), { target: { value: 'upi' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));

    await waitFor(() =>
      expect(buildReport).toHaveBeenCalledWith(
        expect.objectContaining({
          dataset: 'fee_payments',
          filters: [{ field: 'method', op: 'exact', value: 'upi' }],
        }),
      ),
    );
  });

  it('asks for totals when grouping, and for columns when not', async () => {
    render(<ReportBuilder />);
    await choose('fee_payments');

    // Ungrouped: the columns are the choice.
    expect(screen.getByText('Show')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Group by'), { target: { value: 'course' } });
    expect(await screen.findByText('Totals')).toBeInTheDocument();
    expect(screen.queryByText('Show')).not.toBeInTheDocument();
  });

  it('defaults a grouped report to counting, rather than sending no total at all', async () => {
    render(<ReportBuilder />);
    await choose('fee_payments');

    fireEvent.change(screen.getByLabelText('Group by'), { target: { value: 'course' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));

    await waitFor(() =>
      expect(buildReport).toHaveBeenCalledWith(
        expect.objectContaining({ group_by: 'course', measures: ['count'] }),
      ),
    );
  });

  it('starts afresh when the dataset changes', async () => {
    render(<ReportBuilder />);
    await choose('fee_payments');
    fireEvent.change(screen.getByLabelText('Ask about'), { target: { value: 'method' } });
    await screen.findByLabelText('Value');

    fireEvent.change(screen.getByLabelText('Report on'), { target: { value: 'students' } });

    // Carrying "method" across would ask Students about a field it has never
    // heard of, and the server would rightly refuse it.
    await waitFor(() => expect(screen.queryByLabelText('Value')).not.toBeInTheDocument());
    expect(screen.getByText('Everybody on the roll.')).toBeInTheDocument();
  });

  it('says a result was cut rather than letting it read as the whole truth', async () => {
    buildReport.mockResolvedValue({
      columns: [{ name: 'receipt', label: 'Receipt' }],
      rows: [{ receipt: 'GRS-R-00001' }],
      truncated: true,
      grouped: false,
    });
    render(<ReportBuilder />);
    await choose('fee_payments');
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));

    expect(await screen.findByText(/not all of them/)).toBeInTheDocument();
  });

  it('says a grouped answer is grouped', async () => {
    buildReport.mockResolvedValue({
      columns: [
        { name: 'course', label: 'Course' },
        { name: 'count', label: 'Receipts' },
      ],
      rows: [{ course: 'RHCSA', count: 168 }],
      truncated: false,
      grouped: true,
    });
    render(<ReportBuilder />);
    await choose('fee_payments');
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));

    expect(await screen.findByText('grouped')).toBeInTheDocument();
    expect(screen.getByText('168')).toBeInTheDocument();
  });

  it('says what the server refused rather than showing an empty table', async () => {
    buildReport.mockRejectedValue(
      new ApiError(400, 'validation_error', "'city' cannot be asked 'gt'.", 'r1'),
    );
    render(<ReportBuilder />);
    await choose('fee_payments');
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));

    expect(await screen.findByText("'city' cannot be asked 'gt'.")).toBeInTheDocument();
  });
});
