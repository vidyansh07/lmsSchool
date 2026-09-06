import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { StudentPerformance } from '@/app/manage/students/[enrollmentId]/page';
import { ApiError } from '@/lib/api';
import type { StudentPerformanceRow } from '@/lib/manage';
import type { Enrollment } from '@/types/api';

const getEnrollment = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, getEnrollment };
});

const getBatchPerformance = vi.hoisted(() => vi.fn());
const listFeedback = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, getBatchPerformance, listFeedback };
});

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

beforeEach(() => {
  getEnrollment.mockReset();
  getBatchPerformance.mockReset();
  listFeedback.mockReset().mockResolvedValue([]);
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

  it('shows only the feedback matching this student’s code', async () => {
    getEnrollment.mockResolvedValue(enrollment());
    getBatchPerformance.mockResolvedValue([performanceRow()]);
    listFeedback.mockResolvedValue([
      { id: 'fb-1', student_code: 'GRS-S-00001', trainer_code: null, batch_code: 'GRS-B-001', body: 'Great progress this week.', author_name: 'Tina Trainer', created_at: '2026-08-01T00:00:00Z' },
      { id: 'fb-2', student_code: 'GRS-S-00099', trainer_code: null, batch_code: 'GRS-B-001', body: 'Not this student.', author_name: 'Someone Else', created_at: '2026-08-01T00:00:00Z' },
    ]);
    render(<StudentPerformance enrollmentId="enrol-1" />);
    await waitFor(() => expect(screen.getByText('Great progress this week.')).toBeInTheDocument());
    expect(screen.queryByText('Not this student.')).not.toBeInTheDocument();
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
