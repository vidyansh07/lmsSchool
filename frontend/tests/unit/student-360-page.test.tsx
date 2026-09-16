/**
 * Student 360 (ERP Phase 11): the header renders the Phase 12/13
 * placeholders correctly (a neutral "Not yet computed" score and a neutral
 * "No risk signals" badge, never a fabricated number or an alarming empty
 * state), and the tab shown follows `?tab=` so Back and sharing work
 * (DESIGN_DECISIONS.md "Student 360").
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Student360Content } from '@/app/students/[id]/page';
import { ApiError } from '@/lib/api';
import type { Student360Response, StudentProfile, User } from '@/types/api';

const getStudent360 = vi.hoisted(() => vi.fn());
vi.mock('@/lib/student-360', () => ({ getStudent360 }));

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

const push = vi.hoisted(() => vi.fn());
const searchParams = vi.hoisted(() => ({ value: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/students/student-1',
  useSearchParams: () => new URLSearchParams(searchParams.value),
}));

// Each embedded tab has its own dedicated test elsewhere (`timeline.test.tsx`,
// a future `student-activities-tab.test.tsx`); mocking them here keeps this
// suite about the header and the tab wiring, not their own fetches.
vi.mock('@/components/students/student-activities-tab', () => ({
  StudentActivitiesTab: ({ studentId }: { studentId: string }) => <div>Activities tab for {studentId}</div>,
}));
vi.mock('@/components/students/timeline', () => ({
  StudentTimeline: ({ studentId }: { studentId: string }) => <div>Timeline for {studentId}</div>,
}));
vi.mock('@/app/manage/students/[enrollmentId]/page', () => ({
  StudentPerformance: ({ enrollmentId }: { enrollmentId: string }) => <div>Enrolment performance for {enrollmentId}</div>,
}));

function user(overrides: Partial<User> = {}): User {
  return {
    id: 'user-1',
    email: 'asha@example.com',
    first_name: 'Asha',
    last_name: 'Rao',
    full_name: 'Asha Rao',
    phone: '',
    role: 'student',
    is_active: true,
    is_email_verified: true,
    profile_image_url: null,
    date_joined: '2026-01-01',
    branch_id: null,
    branch_code: null,
    branch_name: null,
    ...overrides,
  };
}

function studentProfile(overrides: Partial<StudentProfile> = {}): StudentProfile {
  return {
    id: 'student-1',
    student_id: 'GRS-S-00001',
    user: user(),
    date_of_birth: null,
    address_line1: '',
    address_line2: '',
    city: '',
    state: '',
    country: '',
    postal_code: '',
    qualification: '',
    institution: '',
    institution_kind: '',
    job_title: '',
    roll_number: '',
    graduation_year: null,
    emergency_contact_name: '',
    emergency_contact_phone: '',
    emergency_contact_relationship: '',
    guardian_name: '',
    guardian_phone: '',
    fee_status: 'pending',
    fee_status_updated_at: null,
    fee_amount: null,
    fee_amount_updated_at: null,
    referred_by: null,
    referred_by_label: null,
    completion_percent: 0,
    is_profile_complete: true,
    created_at: '2026-01-01',
    updated_at: '2026-01-01',
    ...overrides,
  };
}

function student360(overrides: Partial<Student360Response> = {}): Student360Response {
  return {
    profile: studentProfile(),
    enrollment: null,
    batch: { id: 'batch-1', code: 'GRS-B-001', name: 'Morning Linux batch' },
    trainer: { id: 'trainer-1', name: 'Tina Trainer' },
    counsellor: { id: 'counsellor-1', name: 'Cara Counsellor' },
    progress: null,
    attendance_summary: { percent: null, attended: null, total_sessions: null, has_records: false },
    performance: { components: [], overall_score: null },
    risk: { level: 'none', triggered: [] },
    counts: { activities_open: 0, activities_overdue: 0, assessments: 0, assignments: 0, projects: 0 },
    fee_status: 'pending',
    recent_activities: [],
    next_actions: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams.value = '';
  useAuth.mockReturnValue({
    user: { id: 'staff-1', role: 'manager', capabilities: ['performance.view_any'] },
    can: (capability: string) => capability === 'performance.view_any',
  });
});

describe('Student360Content', () => {
  it('shows a loading state, then the header once the 360 read model resolves', async () => {
    let resolve!: (value: Student360Response) => void;
    getStudent360.mockReturnValueOnce(
      new Promise((r) => {
        resolve = r;
      }),
    );

    render(<Student360Content studentId="student-1" />);
    expect(screen.getByRole('status')).toBeInTheDocument();

    resolve(student360());
    expect(await screen.findByRole('heading', { name: 'Asha Rao' })).toBeInTheDocument();
  });

  it('renders the Phase 12 performance placeholder as "Not yet computed", never a fabricated score', async () => {
    getStudent360.mockResolvedValueOnce(student360());
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('Not yet computed')).toBeInTheDocument();
  });

  it('renders a real score and a "why" breakdown once Phase 12 supplies components', async () => {
    getStudent360.mockResolvedValueOnce(
      student360({
        performance: {
          overall_score: 82,
          components: [
            { key: 'attendance', label: 'Attendance', weight: 0.5, value: 90, contribution: 45, sources: [] },
          ],
        },
      }),
    );
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('82%')).toBeInTheDocument();
    fireEvent.click(screen.getByText('82%'));
    // Scoped to the popover panel: the Overview tab beneath it already has
    // its own "Attendance" section label, and the fixture's component
    // happens to share that name — `within` disambiguates the two instead
    // of a bare `screen.findByText` that matches both.
    const popover = (await screen.findByText('How this score is built')).closest('div')!;
    expect(within(popover).getByText('Attendance')).toBeInTheDocument();
  });

  it('renders an activity component\'s sources as a per-record breakdown', async () => {
    getStudent360.mockResolvedValueOnce(
      student360({
        performance: {
          overall_score: 74,
          components: [
            { key: 'attendance', label: 'Attendance', weight: 0.4, value: 90, contribution: 36, sources: [] },
            {
              key: 'activity',
              label: 'Activity',
              weight: 0.6,
              value: 63,
              contribution: 38,
              sources: [
                { type: 'Mock interview', score: 70, date: '2026-08-01', trainer: 'Tina Trainer' },
                { type: 'Placement drive', score: 55, date: '2026-08-15', trainer: null },
              ],
            },
          ],
        },
      }),
    );
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('74%')).toBeInTheDocument();
    fireEvent.click(screen.getByText('74%'));

    const popover = (await screen.findByText('How this score is built')).closest('div')!;
    expect(within(popover).getByText('Activity')).toBeInTheDocument();
    expect(within(popover).getByText(/Mock interview.*Tina Trainer/)).toBeInTheDocument();
    expect(within(popover).getByText(/Placement drive/)).toBeInTheDocument();
    // The attendance component here has no sources, so it renders no
    // breakdown list of its own — only the aggregate row.
    expect(within(popover).getAllByText('Attendance')).toHaveLength(1);
  });

  it('renders the Phase 13 risk placeholder as a neutral "No risk signals" badge', async () => {
    getStudent360.mockResolvedValueOnce(student360());
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('No risk signals')).toBeInTheDocument();
  });

  it('renders a real risk level and its triggered rules once Phase 13 supplies them', async () => {
    getStudent360.mockResolvedValueOnce(
      student360({
        risk: {
          level: 'high',
          triggered: [{ key: 'attendance_low', label: 'Low attendance', severity: 'high', detail: '52% attended' }],
        },
      }),
    );
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('High risk')).toBeInTheDocument();
    fireEvent.click(screen.getByText('High risk'));
    expect(await screen.findByText('52% attended')).toBeInTheDocument();
  });

  it('defaults to the Overview tab and switches tabs by pushing `?tab=`', async () => {
    getStudent360.mockResolvedValue(student360());
    render(<Student360Content studentId="student-1" />);
    await screen.findByRole('heading', { name: 'Asha Rao' });

    expect(screen.getByText('Work in progress')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Activities' }));
    expect(push).toHaveBeenCalledWith('/students/student-1?tab=activities');
  });

  it('renders the tab named by `?tab=` in the URL', async () => {
    searchParams.value = 'tab=timeline';
    getStudent360.mockResolvedValue(student360());
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('Timeline for student-1')).toBeInTheDocument();
  });

  it('shows a not-found empty state for a 404, with no header rendered', async () => {
    getStudent360.mockRejectedValueOnce(new ApiError(404, 'not_found', 'No such student.', 'req-1'));
    render(<Student360Content studentId="ghost" />);

    expect(await screen.findByText('Student not found')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /./ })).not.toBeInTheDocument();
  });

  it('shows an error state with a retry that re-fetches', async () => {
    getStudent360.mockRejectedValueOnce(new ApiError(500, 'server_error', 'Down for maintenance.', 'req-2'));
    render(<Student360Content studentId="student-1" />);
    expect(await screen.findByText('Could not load this student')).toBeInTheDocument();

    getStudent360.mockResolvedValueOnce(student360());
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Asha Rao' })).toBeInTheDocument();
  });

  it('hides the Enrolment tab data behind performance.view_any, without a 403 round trip', async () => {
    useAuth.mockReturnValue({
      user: { id: 'staff-2', role: 'counsellor', capabilities: [] },
      can: () => false,
    });
    searchParams.value = 'tab=enrollment';
    getStudent360.mockResolvedValueOnce(student360({ enrollment: { id: 'enrol-1' } as never }));
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('Not available')).toBeInTheDocument();
  });
});
