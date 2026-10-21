/**
 * Student 360 (ERP Phase 11): the header renders the Phase 12/13
 * placeholders correctly (a neutral "Not yet computed" score and a neutral
 * "No risk signals" badge, never a fabricated number or an alarming empty
 * state), and the tab shown follows `?tab=` so Back and sharing work
 * (DESIGN_DECISIONS.md "Student 360").
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Student360Content } from '@/app/students/[id]/page';
import { ApiError } from '@/lib/api';
import type { Student360Response, StudentProfile, User } from '@/types/api';

const getStudent360 = vi.hoisted(() => vi.fn());
vi.mock('@/lib/student-360', () => ({ getStudent360 }));

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

const toast = vi.hoisted(() => vi.fn());
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ toast }) }));
const sendCredentialLink = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, sendCredentialLink };
});
vi.mock('@/components/admissions/plan-follow-up', () => ({
  PlanFollowUp: () => <button type="button">Plan a follow-up</button>,
}));

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
vi.mock('@/components/export-menu', () => ({ ExportMenu: () => null }));
const listCertificates = vi.hoisted(() => vi.fn());
vi.mock('@/lib/progress', async () => {
  const actual = await vi.importActual<typeof import('@/lib/progress')>('@/lib/progress');
  return { ...actual, listCertificates };
});
const listDeliveries = vi.hoisted(() => vi.fn());
vi.mock('@/lib/communication', async () => {
  const actual = await vi.importActual<typeof import('@/lib/communication')>('@/lib/communication');
  return { ...actual, listDeliveries };
});
const getStudentFees = vi.hoisted(() => vi.fn());
vi.mock('@/lib/fees', async () => {
  const actual = await vi.importActual<typeof import('@/lib/fees')>('@/lib/fees');
  return { ...actual, getStudentFees };
});
const listStudentEnrollments = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, listStudentEnrollments };
});
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
    invitation_accepted: true,
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
    area: '',
    landmark: '',
    nationality: '',
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
    about: '',
    career_goal: '',
    interests: [],
    skills: [],
    languages: [],
    preferred_class_time: '',
    linkedin_url: '',
    github_url: '',
    portfolio_url: '',
    open_to_placement: false,
    willing_to_relocate: false,
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

  it('renders the header and Overview for a student whose engines have never run (performance, risk and attendance all null)', async () => {
    getStudent360.mockResolvedValueOnce(
      student360({ performance: null, risk: null, attendance_summary: null }),
    );
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('Not yet computed')).toBeInTheDocument();
    expect(screen.getByText('No risk signals')).toBeInTheDocument();
    expect(screen.getByText('No attendance recorded yet')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/undefined/);
  });

  it('renders a risk level outside the engine\'s three as itself, on a neutral badge, rather than a blank', async () => {
    getStudent360.mockResolvedValueOnce(
      student360({
        risk: { level: 'unknown_import' as NonNullable<Student360Response['risk']>['level'], triggered: [] },
      }),
    );
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('Unknown Import')).toBeInTheDocument();
  });

  it('renders the Phase 13 risk placeholder as a neutral "No risk signals" badge', async () => {
    getStudent360.mockResolvedValueOnce(student360());
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('No risk signals')).toBeInTheDocument();
  });

  it('renders a real risk level and its triggered rules once the risk engine supplies them', async () => {
    getStudent360.mockResolvedValueOnce(
      student360({
        risk: {
          level: 'critical',
          triggered: [
            {
              key: 'attendance',
              label: 'Attendance',
              severity: 'critical',
              detail: '52% attended, below the 75% risk threshold.',
              numbers: { percent: 52, threshold: '75' },
            },
          ],
        },
      }),
    );
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('Critical')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Critical'));
    expect(await screen.findByText('52% attended, below the 75% risk threshold.')).toBeInTheDocument();
  });

  it('renders the Risk tab with the triggered rule, its severity and its numbers', async () => {
    searchParams.value = 'tab=risk';
    getStudent360.mockResolvedValueOnce(
      student360({
        risk: {
          level: 'warning',
          triggered: [
            {
              key: 'academic',
              label: 'Assessment average',
              severity: 'warning',
              detail: '58% average, below the 60% risk threshold.',
              numbers: { percent: 58, threshold: '60' },
            },
          ],
        },
      }),
    );
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('Current risk level')).toBeInTheDocument();
    expect(screen.getByText('Assessment average')).toBeInTheDocument();
    expect(screen.getByText('58% average, below the 60% risk threshold.')).toBeInTheDocument();
    // The raw numbers sit behind a "Numbers" disclosure rather than being
    // shown by default.
    expect(screen.getByText('Numbers')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Numbers'));
    expect(screen.getByText('58')).toBeInTheDocument();
  });

  it('renders the Risk tab\'s "no risk signals" copy unchanged for a `none` level', async () => {
    searchParams.value = 'tab=risk';
    getStudent360.mockResolvedValueOnce(student360());
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('Current risk level')).toBeInTheDocument();
    expect(screen.getAllByText('No risk signals').length).toBeGreaterThan(0);
  });

  it('switches to the Risk tab via `?tab=risk` like the other tabs', async () => {
    getStudent360.mockResolvedValue(student360());
    render(<Student360Content studentId="student-1" />);
    await screen.findByRole('heading', { name: 'Asha Rao' });

    fireEvent.click(screen.getByRole('tab', { name: 'Risk' }));
    expect(push).toHaveBeenCalledWith('/students/student-1?tab=risk');
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

describe('Student360Content — fees and the other records', () => {
  it('offers the fee ledger to someone who reads fees, and links the admissions record and the account', async () => {
    useAuth.mockReturnValue({
      user: { id: 'staff-1', role: 'counsellor', capabilities: [] },
      can: (capability: string) =>
        ['fee.view_any', 'enrolment.create', 'user.view_any'].includes(capability),
    });
    getStudent360.mockResolvedValue(student360());
    getStudentFees.mockResolvedValue({
      student_id: 'student-1',
      fee_status: 'paid',
      plans: [],
      totals: { agreed: '0', discount: '0', payable: '0', paid: '0', balance: '0' },
    });
    listStudentEnrollments.mockResolvedValue([]);
    searchParams.value = 'tab=fees';
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByRole('tab', { name: 'Fees' })).toBeInTheDocument();
    await waitFor(() => expect(getStudentFees).toHaveBeenCalledWith('student-1'));
    expect(screen.getByRole('link', { name: 'Admissions record' })).toHaveAttribute(
      'href',
      '/admissions/student-1',
    );
    expect(screen.getByRole('link', { name: 'Account' })).toBeInTheDocument();
  });

  it('has no Fees tab for someone who cannot read fees', async () => {
    getStudent360.mockResolvedValue(student360());
    render(<Student360Content studentId="student-1" />);
    expect(await screen.findByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Fees' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Account' })).toBeNull();
  });
});

describe('Student360Content — messages and certificates', () => {
  it('lists the certificates awarded to this student, with a verify link', async () => {
    getStudent360.mockResolvedValue(student360());
    listCertificates.mockResolvedValue({
      count: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
      results: [
        {
          id: 'c1',
          number: 'GRS-CERT-0001',
          verification_code: 'ABC123',
          course_title: 'Linux Essentials',
          batch_code: 'GRS-B-001',
          completion_date: '2026-09-30',
          status: 'issued',
          is_live: true,
          issued_at: '2026-10-01T00:00:00Z',
        },
      ],
    });
    searchParams.value = 'tab=certificates';
    render(<Student360Content studentId="student-1" />);

    await waitFor(() => expect(listCertificates).toHaveBeenCalledWith({ student: 'student-1' }));
    expect(await screen.findByText('GRS-CERT-0001')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Verify' })).toHaveAttribute('href', '/verify/ABC123');
  });

  it('shows the messages tab only to someone who reads the delivery log', async () => {
    useAuth.mockReturnValue({
      user: { id: 'staff-1', role: 'admin', capabilities: [] },
      can: (capability: string) => capability === 'communication.view_any',
    });
    getStudent360.mockResolvedValue(student360());
    listDeliveries.mockResolvedValue({ count: 0, page: 1, page_size: 20, total_pages: 1, results: [] });
    searchParams.value = 'tab=messages';
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByText('No messages yet')).toBeInTheDocument();
    expect(listDeliveries).toHaveBeenCalledWith(expect.objectContaining({ recipient: expect.any(String) }));
  });
});

describe('Student360Content — actions for this student', () => {
  it('offers the desk\'s actions by capability, each landing where the work is done', async () => {
    const capabilities = [
      'fee.manage_any',
      'enrolment.create',
      'enrolment.update_any',
      'user.update_any',
      'activity.create',
    ];
    useAuth.mockReturnValue({
      user: { id: 'staff-1', role: 'counsellor', capabilities },
      can: (capability: string) => capabilities.includes(capability),
    });
    getStudent360.mockResolvedValue(
      student360({ profile: studentProfile({ user: user({ invitation_accepted: false }) }) }),
    );
    sendCredentialLink.mockResolvedValue({ sent: true, detail: 'ok' });
    render(<Student360Content studentId="student-1" />);

    expect(await screen.findByRole('button', { name: 'Plan a follow-up' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Actions' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Record a payment' }));
    expect(push).toHaveBeenCalledWith('/students/student-1?tab=fees');

    fireEvent.click(screen.getByRole('button', { name: 'Actions' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Move to another batch' }));
    expect(push).toHaveBeenCalledWith('/admissions/transfer?student=student-1');

    fireEvent.click(screen.getByRole('button', { name: 'Actions' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Resend invitation' }));
    fireEvent.click(screen.getByRole('button', { name: 'Send invitation' }));
    // A set-password invitation (the server sends one to an account that has
    // no password yet), not a verify-email link.
    await waitFor(() => expect(sendCredentialLink).toHaveBeenCalledWith('user-1', 'password_reset'));
  });

  it('offers no actions to somebody who can only read', async () => {
    getStudent360.mockResolvedValue(student360());
    render(<Student360Content studentId="student-1" />);
    await screen.findByText('GRS-S-00001');
    expect(screen.queryByRole('button', { name: 'Actions' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Plan a follow-up' })).not.toBeInTheDocument();
  });
});
