import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { StudentPerformance } from '@/app/manage/students/[enrollmentId]/page';
import { ApiError } from '@/lib/api';
import type { FeedbackItem, StudentPerformanceRow } from '@/lib/manage';
import type { Enrollment } from '@/types/api';

const getEnrollment = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, getEnrollment };
});

const getBatchPerformance = vi.hoisted(() => vi.fn());
const listFeedback = vi.hoisted(() => vi.fn());
const createFeedback = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, getBatchPerformance, listFeedback, createFeedback };
});

const listReviews = vi.hoisted(() => vi.fn());
vi.mock('@/lib/performance', async () => {
  const actual = await vi.importActual<typeof import('@/lib/performance')>('@/lib/performance');
  return { ...actual, listReviews };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

function enrollment(overrides: Partial<Enrollment> = {}): Enrollment {
  return {
    id: 'enrol-1',
    code: 'GRS-E-00001',
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    batch_id: 'batch-1',
    batch_code: 'GRS-B-001',
    batch_name: 'Morning Linux batch',
    batch_status: 'active',
    trainer_name: 'Tina Trainer',
    status: 'active',
    enrolled_at: '2026-04-01',
    start_date: '2026-04-01',
    access_end_date: null,
    completed_at: null,
    grants_access: true,
    student_id: 'student-1',
    student_code: 'GRS-S-00001',
    student_name: 'Jane Student',
    student_email: 'jane@example.com',
    ...overrides,
  };
}

function performanceRow(overrides: Partial<StudentPerformanceRow> = {}): StudentPerformanceRow {
  return {
    enrollment_id: 'enrol-1',
    course_title: 'Linux Essentials',
    batch_code: 'GRS-B-001',
    attendance: { percent: 90, total_sessions: 10, attended: 9, has_records: true },
    assessment: { average_percent: 78, sitting_percent: 100, recorded: 3, total: 3 },
    assignments: { percent: 80, total: 5, submitted: 4, graded: 4, passed: 4, missed: 0 },
    projects: { percent: 100, required: 1, finished: 1 },
    progress: { percent: 40, expected_percent: 45, variance: 5 },
    overall_score: 82,
    risk: { at_risk: false, outcomes: [], triggered: [], triggered_count: 0 },
    ...overrides,
  };
}

function feedbackItem(overrides: Partial<FeedbackItem> = {}): FeedbackItem {
  return {
    id: 'fb-1',
    student_code: 'GRS-S-00001',
    trainer_code: null,
    batch_code: 'GRS-B-001',
    body: 'Great progress this week.',
    visible_to_subject: true,
    author_name: 'Tina Trainer',
    created_at: '2026-08-01T00:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  getEnrollment.mockReset();
  getBatchPerformance.mockReset();
  listFeedback.mockReset().mockResolvedValue([]);
  createFeedback.mockReset().mockResolvedValue({});
  listReviews.mockReset().mockResolvedValue([]);
  useAuth.mockReset().mockReturnValue({ can: () => true });
});

describe('StudentPerformance', () => {
  it('renders the student header and batch link', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Jane Student' })).toBeInTheDocument());
    expect(screen.getByText('GRS-S-00001')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Morning Linux batch' })).toHaveAttribute(
      'href',
      '/manage/batches/batch-1',
    );
  });

  it('surfaces every triggered risk outcome with its own explanatory sentence', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([
      performanceRow({
        risk: {
          at_risk: true,
          triggered: ['attendance'],
          triggered_count: 1,
          outcomes: [
            {
              key: 'attendance',
              label: 'Attendance',
              triggered: true,
              severity: 'warning',
              detail: '68% attended, below the 75% risk threshold.',
            },
            {
              key: 'academic',
              label: 'Assessment average',
              triggered: false,
              severity: 'none',
              detail: '80% average, at or above the 70% risk threshold.',
            },
          ],
        },
      }),
    ]);
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByTestId('student-risk-banner')).toBeInTheDocument());
    expect(screen.getByText(/68% attended, below the 75% risk threshold/)).toBeInTheDocument();
    // Only the triggered outcome is listed as a concern.
    expect(screen.queryByText(/80% average, at or above/)).not.toBeInTheDocument();
  });

  it('shows no risk banner, and does not crash, for an enrolment the risk engine has never evaluated', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow({ risk: null })]);
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Jane Student' })).toBeInTheDocument());
    expect(screen.queryByTestId('student-risk-banner')).not.toBeInTheDocument();
  });

  it('shows no risk banner for a student who is not flagged', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Jane Student' })).toBeInTheDocument());
    expect(screen.queryByTestId('student-risk-banner')).not.toBeInTheDocument();
  });

  it('says plainly when no classes have been registered yet, rather than "0%"', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([
      performanceRow({ attendance: { percent: null, total_sessions: 0, attended: 0, has_records: false } }),
    ]);
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByText('No classes have been registered yet.')).toBeInTheDocument());
  });

  it('renders assessment, assignment and project figures', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByText('78%')).toBeInTheDocument());
    expect(screen.getByText('4 / 5')).toBeInTheDocument();
    expect(screen.getByText('1 / 1')).toBeInTheDocument();
  });

  it('renders fallbacks for every nullable performance figure, never a raw NaN', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([
      performanceRow({
        assessment: { average_percent: null, sitting_percent: null, recorded: 0, total: 0 },
        assignments: { percent: null, total: 0, submitted: 0, graded: 0, passed: 0, missed: 0 },
        projects: { percent: null, required: 0, finished: 0 },
        progress: { percent: null, expected_percent: null, variance: null },
        overall_score: null,
      }),
    ]);
    const { container } = render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Jane Student' })).toBeInTheDocument());
    expect(container.textContent).not.toMatch(/NaN|undefined|Invalid Date/);
    expect(screen.getAllByText('No data').length).toBeGreaterThan(0);
  });

  it('renders an empty state when the enrolment has no performance row yet, without crashing', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([]);
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByText('No performance data yet')).toBeInTheDocument());
  });

  it('loads feedback independently and shows its own empty state', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    listFeedback.mockResolvedValue([]);
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByText('No feedback yet')).toBeInTheDocument());
  });

  it('asks the server for this student’s feedback rather than filtering the whole visible set', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    listFeedback.mockResolvedValue([feedbackItem()]);
    render(<StudentPerformance enrollmentId="enrol-1" />);

    await waitFor(() => expect(screen.getByText('Great progress this week.')).toBeInTheDocument());
    // The id, not the code: `?student=` is applied after the endpoint's own
    // scoping, so it can narrow the list and never widen it.
    expect(listFeedback).toHaveBeenCalledWith('student-1');
  });

  it('marks feedback the student cannot read, so staff know which kind it is', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    listFeedback.mockResolvedValue([
      feedbackItem({ id: 'fb-1', body: 'Shown to them.' }),
      feedbackItem({ id: 'fb-2', body: 'A note for the next review.', visible_to_subject: false }),
    ]);
    render(<StudentPerformance enrollmentId="enrol-1" />);

    await waitFor(() => expect(screen.getByText('Shown to them.')).toBeInTheDocument());
    expect(screen.getAllByText('Staff only')).toHaveLength(1);
  });

  it('leaves feedback about the student and reloads the list', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    render(<StudentPerformance enrollmentId="enrol-1" />);

    await waitFor(() => expect(screen.getByText('No feedback yet')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Leave feedback/i }));
    expect(screen.getByText('Feedback for Jane Student')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Feedback'), {
      target: { value: 'Asked good questions today.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save feedback' }));

    await waitFor(() =>
      expect(createFeedback).toHaveBeenCalledWith({
        student: 'student-1',
        body: 'Asked good questions today.',
        visibleToSubject: true,
      }),
    );
    // Reloaded, rather than the new row being pushed into local state where
    // it could disagree with what the server actually stored.
    await waitFor(() => expect(listFeedback).toHaveBeenCalledTimes(2));
  });

  it('can keep a note off the student’s own dashboard', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    render(<StudentPerformance enrollmentId="enrol-1" />);

    await waitFor(() => expect(screen.getByText('No feedback yet')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Leave feedback/i }));
    fireEvent.change(screen.getByLabelText('Feedback'), { target: { value: 'For the review.' } });
    fireEvent.click(screen.getByLabelText(/Show this to the student/));
    fireEvent.click(screen.getByRole('button', { name: 'Save feedback' }));

    await waitFor(() =>
      expect(createFeedback).toHaveBeenCalledWith({
        student: 'student-1',
        body: 'For the review.',
        visibleToSubject: false,
      }),
    );
  });

  it('writes nothing when the feedback is blank', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    render(<StudentPerformance enrollmentId="enrol-1" />);

    await waitFor(() => expect(screen.getByText('No feedback yet')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Leave feedback/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Save feedback' }));

    expect(await screen.findByText('Write the feedback before saving.')).toBeInTheDocument();
    expect(createFeedback).not.toHaveBeenCalled();
  });

  it('offers no way to write feedback to somebody who may only read it', async () => {
    useAuth.mockReturnValue({ can: () => false });
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    listFeedback.mockResolvedValue([feedbackItem()]);
    render(<StudentPerformance enrollmentId="enrol-1" />);

    await waitFor(() => expect(screen.getByText('Great progress this week.')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /Leave feedback/i })).not.toBeInTheDocument();
  });

  it('shows a not-found state for an enrolment that does not exist or is not visible', async () => {
    getEnrollment.mockRejectedValue(new ApiError(404, 'not_found', 'Not found.', 'req-1'));
    render(<StudentPerformance enrollmentId="missing" />);
    await waitFor(() => expect(screen.getByText('Enrolment not found')).toBeInTheDocument());
  });

  it('shows a retryable error for anything other than a 404', async () => {
    getEnrollment.mockRejectedValue(new ApiError(500, 'server_error', 'Something broke.', 'req-2'));
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByText('Something broke.')).toBeInTheDocument());
  });
});
