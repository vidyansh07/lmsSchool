import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BatchRoster } from '@/app/manage/batches/[batchId]/students/page';
import { ApiError } from '@/lib/api';
import type { BatchStudentRow } from '@/lib/manage';

const listBatchStudents = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, listBatchStudents };
});

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

function page(results: BatchStudentRow[]) {
  return { count: results.length, page: 1, page_size: 25, total_pages: 1, next: null, previous: null, results };
}

function studentRow(overrides: Partial<BatchStudentRow> = {}): BatchStudentRow {
  return {
    enrollment_id: 'enrol-1',
    student_id: 'GRS-S-00001',
    name: 'Jane Student',
    status: 'active',
    attendance_percent: 88,
    assessment_average: 74,
    assignments_submitted: 4,
    assignments_total: 5,
    projects_submitted: 1,
    projects_total: 2,
    progress_percent: 55,
    risk_flags: [],
    transferred_in: false,
    ...overrides,
  };
}

beforeEach(() => {
  listBatchStudents.mockReset();
  push.mockReset();
});

describe('BatchRoster', () => {
  it('renders a student row with attendance, assessment and progress figures', async () => {
    listBatchStudents.mockResolvedValue(page([studentRow()]));
    render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Jane Student')).toBeInTheDocument());
    expect(screen.getByText('88%')).toBeInTheDocument();
    expect(screen.getByText('74%')).toBeInTheDocument();
    expect(screen.getByText('55%')).toBeInTheDocument();
  });

  it('marks a student who transferred in from another batch', async () => {
    listBatchStudents.mockResolvedValue(page([studentRow({ transferred_in: true })]));
    render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Transferred')).toBeInTheDocument());
  });

  it('does not mark an ordinary enrolment as transferred', async () => {
    listBatchStudents.mockResolvedValue(page([studentRow({ transferred_in: false })]));
    render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Jane Student')).toBeInTheDocument());
    expect(screen.queryByText('Transferred')).not.toBeInTheDocument();
  });

  it('renders risk flags with their own text', async () => {
    listBatchStudents.mockResolvedValue(page([studentRow({ risk_flags: ['attendance'] })]));
    render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Attendance')).toBeInTheDocument());
  });

  it('reads a clean record as "On track" rather than an empty cell', async () => {
    listBatchStudents.mockResolvedValue(page([studentRow({ risk_flags: [] })]));
    render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('On track')).toBeInTheDocument());
  });

  it('renders fallbacks for every nullable rollup field, never a blank or NaN', async () => {
    listBatchStudents.mockResolvedValue(
      page([
        studentRow({
          attendance_percent: null,
          assessment_average: null,
          progress_percent: null,
        }),
      ]),
    );
    const { container } = render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Jane Student')).toBeInTheDocument());
    expect(screen.getAllByText('No data').length).toBe(3);
    expect(container.textContent).not.toMatch(/NaN|undefined/);
  });

  it('shows an empty state when nobody is enrolled', async () => {
    listBatchStudents.mockResolvedValue(page([]));
    render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('No students match these filters')).toBeInTheDocument());
  });

  it('shows an error with retry on failure', async () => {
    listBatchStudents.mockRejectedValue(new ApiError(500, 'server_error', 'Could not load the roster.', 'req-1'));
    render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Could not load the roster.')).toBeInTheDocument());
  });

  it('sends search and sort to the server rather than filtering client-side', async () => {
    listBatchStudents.mockResolvedValue(page([studentRow()]));
    render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(listBatchStudents).toHaveBeenCalledTimes(1));

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Search'), 'jane');
    await waitFor(() =>
      expect(listBatchStudents).toHaveBeenLastCalledWith('batch-1', expect.objectContaining({ search: 'jane' })),
    );

    await user.click(screen.getByRole('button', { name: /attendance/i }));
    await waitFor(() =>
      expect(listBatchStudents).toHaveBeenLastCalledWith(
        'batch-1',
        expect.objectContaining({ ordering: 'attendance_percent' }),
      ),
    );
  });

  it('opens the student on row activation', async () => {
    listBatchStudents.mockResolvedValue(page([studentRow()]));
    render(<BatchRoster batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Jane Student')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByText('Jane Student'));
    expect(push).toHaveBeenCalledWith('/manage/students/enrol-1');
  });
});
