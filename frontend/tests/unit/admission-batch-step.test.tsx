/**
 * Batch Details — the registration step that had a name and no page.
 *
 * The step bar has listed "Batch Details" since the desk flow was built and
 * nothing implemented it, so that flow ended at the payment screen: a student
 * registered, billed, and on no batch at all. What is pinned here is that the
 * screen says that plainly, that a course is enrolled once, and that opening a
 * new batch whose trainer cannot be assigned still leaves the batch opened —
 * a clash must not silently lose the work.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BatchStep } from '@/app/students/[id]/admissions/[admissionId]/batch/page';
import { ApiError } from '@/lib/api';
import type { Admission, AdmissionLine } from '@/lib/admissions-api';

const getAdmission = vi.hoisted(() => vi.fn());
const enrolAdmissionLine = vi.hoisted(() => vi.fn());
vi.mock('@/lib/admissions-api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/admissions-api')>(
    '@/lib/admissions-api',
  );
  return { ...actual, getAdmission, enrolAdmissionLine };
});

const listBatches = vi.hoisted(() => vi.fn());
const createBatch = vi.hoisted(() => vi.fn());
const assignBatchTrainer = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, listBatches, createBatch, assignBatchTrainer };
});

const listTrainers = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, listTrainers };
});

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

function line(overrides: Partial<AdmissionLine> = {}): AdmissionLine {
  return {
    id: 'line-1',
    kind: 'course',
    course_id: 'course-1',
    course_title: 'RHCSA',
    label: 'RHCSA',
    name: 'RHCSA',
    charged_on_id: null,
    quantity: 1,
    unit_fee: '20000.00',
    line_total: '20000.00',
    discount_share: '0.00',
    enrollment_id: null,
    ...overrides,
  };
}

function admission(lines: AdmissionLine[]): Admission {
  return {
    id: 'adm-1',
    student_id: 'stu-1',
    student_name: 'Aarti Sharma',
    branch_id: 'b1',
    branch_name: 'Jaipur',
    academic_year_id: null,
    academic_year: null,
    admission_date: '2026-10-26',
    status: 'active',
    is_cancelled: false,
    discount_kind: 'flat',
    discount_amount: '0.00',
    discount_percent: null,
    gross_total: '20000.00',
    total_fees: '20000.00',
    note: '',
    money: {
      total: '20000.00',
      paid: '0.00',
      uncleared: '0.00',
      refund: '0.00',
      balance: '20000.00',
    },
    lines,
    created_by: null,
    cancelled_at: null,
    cancellation_reason: '',
    created_at: '2026-10-26T09:00:00Z',
    updated_at: '2026-10-26T09:00:00Z',
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listTrainers.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  listBatches.mockResolvedValue({
    count: 1,
    next: null,
    previous: null,
    results: [
      {
        id: 'batch-1',
        name: 'Morning batch',
        code: 'GRS-B-0007',
        start_date: '2026-11-03',
        trainer_name: 'Rahul K',
      },
    ],
  });
});

describe('BatchStep', () => {
  it('says what is still missing, in the words that matter', async () => {
    getAdmission.mockResolvedValue(admission([line()]));
    render(<BatchStep studentId="stu-1" admissionId="adm-1" />);

    expect(await screen.findByText(/One course still needs a batch/)).toBeInTheDocument();
    expect(screen.getByText(/registered and billed but not timetabled/)).toBeInTheDocument();
    expect(screen.getByText('Not on a batch yet')).toBeInTheDocument();
  });

  it('enrols onto a batch that already runs the course', async () => {
    getAdmission.mockResolvedValue(admission([line()]));
    enrolAdmissionLine.mockResolvedValue(
      admission([line({ enrollment_id: 'enr-1' })]),
    );
    render(<BatchStep studentId="stu-1" admissionId="adm-1" />);

    await screen.findByText('Not on a batch yet');
    await waitFor(() => expect(listBatches).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText(/Batch/), { target: { value: 'batch-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enrol onto this batch' }));

    await waitFor(() =>
      expect(enrolAdmissionLine).toHaveBeenCalledWith('adm-1', 'line-1', 'batch-1'),
    );
    expect(await screen.findByText('Enrolled')).toBeInTheDocument();
  });

  it('only lists batches teaching that course', async () => {
    getAdmission.mockResolvedValue(admission([line()]));
    render(<BatchStep studentId="stu-1" admissionId="adm-1" />);

    await screen.findByText('Not on a batch yet');
    await waitFor(() =>
      expect(listBatches).toHaveBeenCalledWith({ course: 'course-1', page_size: 50 }),
    );
  });

  it('keeps a newly opened batch when its trainer clashes', async () => {
    getAdmission.mockResolvedValue(admission([line()]));
    createBatch.mockResolvedValue({ id: 'batch-new', name: 'Evening', code: 'GRS-B-0008' });
    assignBatchTrainer.mockRejectedValue(
      new ApiError(409, 'conflict', 'Rahul K already teaches then.', 'r1'),
    );
    enrolAdmissionLine.mockResolvedValue(admission([line({ enrollment_id: 'enr-2' })]));
    listTrainers.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 'tr-1', full_name: 'Rahul K' }],
    });
    render(<BatchStep studentId="stu-1" admissionId="adm-1" />);

    await screen.findByText('Not on a batch yet');
    fireEvent.click(screen.getByRole('radio', { name: 'Open a new one' }));
    fireEvent.change(screen.getByLabelText(/Batch name/), { target: { value: 'Evening' } });
    fireEvent.change(screen.getByLabelText('Trainer'), { target: { value: 'tr-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enrol onto this batch' }));

    // The batch was opened and the student enrolled; only the trainer failed,
    // and the message says which.
    await waitFor(() =>
      expect(enrolAdmissionLine).toHaveBeenCalledWith('adm-1', 'line-1', 'batch-new'),
    );
    expect(await screen.findByText(/already teaches then/)).toBeInTheDocument();
  });

  it('offers nothing on a course that is already enrolled', async () => {
    getAdmission.mockResolvedValue(admission([line({ enrollment_id: 'enr-1' })]));
    render(<BatchStep studentId="stu-1" admissionId="adm-1" />);

    expect(await screen.findByText('Enrolled')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Enrol onto this batch' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/Every course on this admission is on a batch/)).toBeInTheDocument();
  });

  it('will not finish while a course is still unplaced', async () => {
    getAdmission.mockResolvedValue(admission([line(), line({ id: 'line-2', name: 'AWS' })]));
    render(<BatchStep studentId="stu-1" admissionId="adm-1" />);

    expect(await screen.findByText(/2 courses still need a batch/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Finish' })).toBeDisabled();
  });

  it('lists an additional fee nowhere — a fee is not enrolled onto anything', async () => {
    getAdmission.mockResolvedValue(
      admission([
        line(),
        line({ id: 'line-3', kind: 'additional_fee', name: 'Exam fee', course_id: null }),
      ]),
    );
    const { container } = render(<BatchStep studentId="stu-1" admissionId="adm-1" />);

    await screen.findByText('RHCSA');
    expect(within(container).queryByText('Exam fee')).not.toBeInTheDocument();
  });
});
