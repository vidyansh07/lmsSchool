/**
 * Integration coverage for the counsellor dashboard: `AdmissionsDashboardContent`
 * (exported so it can be mounted with mocked `lib/*` calls, sidestepping
 * `useAuth` the same way `RegistrationWizard` and `AdmissionsList` already do
 * in this test suite) and the capability gate on the default export.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AdmissionsDashboardPage, { AdmissionsDashboardContent } from '@/app/admissions/dashboard/page';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import type { BatchListRow, Enrollment, Paginated, StudentListRow } from '@/types/api';

const listStudents = vi.hoisted(() => vi.fn());
const listBatches = vi.hoisted(() => vi.fn());
const listEnrollments = vi.hoisted(() => vi.fn());
const useAuthMock = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));

vi.mock('@/lib/people', () => ({ listStudents }));
vi.mock('@/lib/batches', () => ({ listBatches, listEnrollments }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => useAuthMock.value }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/admissions/dashboard',
}));

function paginated<T>(results: T[], count = results.length): Paginated<T> {
  return { count, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function student(overrides: Partial<StudentListRow> = {}): StudentListRow {
  return {
    id: 'student-1',
    student_id: 'GRS-S-00001',
    user_id: 'u1',
    email: 'new.student@example.com',
    full_name: 'New Student',
    city: 'Jaipur',
    qualification: 'bachelors',
    fee_status: 'pending',
    fee_amount: null,
    institution: '',
    roll_number: '',
    institution_kind: '',
    referred_by: null,
    is_active: true,
    is_email_verified: false,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

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
    batch_name: 'Morning batch',
    batch_status: 'active',
    trainer_name: '',
    status: 'active',
    enrolled_at: new Date().toISOString(),
    start_date: null,
    access_end_date: null,
    completed_at: null,
    grants_access: true,
    student_id: 'student-1',
    student_code: 'GRS-S-00001',
    student_name: 'New Student',
    student_email: 'new.student@example.com',
    ...overrides,
  };
}

function batch(overrides: Partial<BatchListRow> = {}): BatchListRow {
  return {
    id: 'batch-1',
    code: 'GRS-B-001',
    name: 'Morning batch',
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    trainer_name: '',
    start_date: '2026-04-01',
    end_date: '2026-06-01',
    capacity: 20,
    enrolled_count: 5,
    seats_available: 15,
    status: 'upcoming',
    created_at: '2026-01-01',
    ...overrides,
  };
}

/**
 * Several student names legitimately appear more than once on this page —
 * a registration recent enough to be "not yet enrolled" is, by definition,
 * also recent enough to be in "recent activity". Scoping a query to one
 * card by its heading, rather than searching the whole document, is how
 * these tests stay meaningful instead of failing on that overlap.
 */
function cardFor(titleText: string | RegExp): HTMLElement {
  const heading = screen.getByRole('heading', { name: titleText });
  const card = heading.parentElement?.parentElement;
  if (!card) throw new Error(`Could not locate the card for "${String(titleText)}"`);
  return card as HTMLElement;
}

function mockEmptyPipeline() {
  listStudents.mockResolvedValue(paginated<StudentListRow>([]));
  listEnrollments.mockImplementation((query: Record<string, unknown> = {}) =>
    Promise.resolve(paginated<Enrollment>([], query.status === 'pending' ? 0 : 0)),
  );
  listBatches.mockResolvedValue(paginated<BatchListRow>([]));
}

describe('AdmissionsDashboardContent', () => {
  it('puts "Register a student" first among the quick actions, reachable immediately', async () => {
    mockEmptyPipeline();
    render(<AdmissionsDashboardContent />);

    const registerLink = await screen.findByRole('link', { name: /register a student/i });
    expect(registerLink).toHaveAttribute('href', '/admissions/new');

    const allLinks = screen.getAllByRole('link');
    expect(allLinks.indexOf(registerLink)).toBe(0);
  });

  it('also surfaces "Create a batch" and "Bulk import" as real, keyboard-reachable links', async () => {
    mockEmptyPipeline();
    render(<AdmissionsDashboardContent />);
    expect(await screen.findByRole('link', { name: /create a batch/i })).toHaveAttribute(
      'href',
      '/admissions/batches',
    );
    expect(screen.getByRole('link', { name: /bulk import/i })).toHaveAttribute(
      'href',
      '/admissions/import',
    );
  });

  it('renders the "registered, not yet enrolled" list and links each row to that student', async () => {
    listStudents.mockResolvedValue(paginated<StudentListRow>([student()]));
    listEnrollments.mockImplementation((query: Record<string, unknown> = {}) =>
      Promise.resolve(paginated<Enrollment>([], query.status === 'pending' ? 0 : 0)),
    );
    listBatches.mockResolvedValue(paginated<BatchListRow>([]));

    render(<AdmissionsDashboardContent />);

    await waitFor(() => expect(screen.getByText(/1 of the last 1 registration/i)).toBeInTheDocument());
    const scope = within(cardFor('Registered, not yet enrolled'));
    expect(scope.getByRole('link', { name: /new student/i })).toHaveAttribute(
      'href',
      '/admissions/student-1',
    );
  });

  it('does not list a student whose enrolment already appears in the recent enrolments window', async () => {
    listStudents.mockResolvedValue(paginated<StudentListRow>([student()]));
    listEnrollments.mockImplementation((query: Record<string, unknown> = {}) =>
      Promise.resolve(
        paginated<Enrollment>(query.status === 'pending' ? [] : [enrollment()], query.status === 'pending' ? 0 : 1),
      ),
    );
    listBatches.mockResolvedValue(paginated<BatchListRow>([]));

    render(<AdmissionsDashboardContent />);

    await waitFor(() => expect(listStudents).toHaveBeenCalled());
    expect(await screen.findByText(/every recent registration is enrolled/i)).toBeInTheDocument();
    const scope = within(cardFor('Registered, not yet enrolled'));
    expect(scope.queryByRole('link', { name: /new student/i })).not.toBeInTheDocument();
  });

  it('shows the exact pending-confirmation total from the server, not the capped page size', async () => {
    listStudents.mockResolvedValue(paginated<StudentListRow>([]));
    listEnrollments.mockImplementation((query: Record<string, unknown> = {}) =>
      Promise.resolve(
        paginated<Enrollment>(query.status === 'pending' ? [enrollment()] : [], query.status === 'pending' ? 12 : 0),
      ),
    );
    listBatches.mockResolvedValue(paginated<BatchListRow>([]));

    render(<AdmissionsDashboardContent />);
    expect(await screen.findByText(/12 awaiting confirmation/)).toBeInTheDocument();
  });

  it('separates "starting soon" from "filling up" batches', async () => {
    mockEmptyPipeline();
    listBatches.mockImplementation((query: Record<string, unknown> = {}) => {
      if (query.status === 'upcoming') {
        return Promise.resolve(
          paginated<BatchListRow>([batch({ id: 'soon', status: 'upcoming', seats_available: 15, capacity: 20 })]),
        );
      }
      return Promise.resolve(
        paginated<BatchListRow>([
          batch({ id: 'tight', status: 'active', seats_available: 1, capacity: 20, start_date: '2026-01-01' }),
        ]),
      );
    });

    render(<AdmissionsDashboardContent />);
    expect(await screen.findByText(/starts/i)).toBeInTheDocument();
    expect(await screen.findByText('1 seat left')).toBeInTheDocument();
  });

  it('shows an error with a working retry when a bucket fails, without blocking the rest of the page', async () => {
    listStudents.mockRejectedValue(new ApiError(500, 'server_error', 'Registrations are down.', 'req-1'));
    listEnrollments.mockResolvedValue(paginated<Enrollment>([]));
    listBatches.mockResolvedValue(paginated<BatchListRow>([]));

    render(<AdmissionsDashboardContent />);
    // Both the not-yet-enrolled panel and the recent-activity panel depend on
    // the same failed `recentStudents` bucket, so the message legitimately
    // appears twice — `findAllByText` is the honest assertion here, not a
    // narrower query pretending there is only one.
    const messages = await screen.findAllByText('Registrations are down.');
    expect(messages.length).toBeGreaterThan(0);
    // A different, healthy section still rendered its own content.
    expect(await screen.findByText(/nothing pending/i)).toBeInTheDocument();
  });

  it('renders every KPI without a raw undefined or NaN while data is still loading', () => {
    listStudents.mockReturnValue(new Promise(() => {}));
    listEnrollments.mockReturnValue(new Promise(() => {}));
    listBatches.mockReturnValue(new Promise(() => {}));

    render(<AdmissionsDashboardContent />);
    const bodyText = document.body.textContent ?? '';
    expect(bodyText).not.toMatch(/undefined/);
    expect(bodyText).not.toMatch(/\bNaN\b/);
  });
});

describe('AdmissionsDashboardPage — capability gate', () => {
  it('renders the dashboard for a counsellor holding enrolment.create', async () => {
    useAuthMock.value = {
      user: { id: 'u1', role: 'counsellor', capabilities: [Capability.enrolmentCreate] },
      isLoading: false,
      can: (capability: string) => capability === Capability.enrolmentCreate,
    };
    mockEmptyPipeline();

    render(<AdmissionsDashboardPage />);
    expect(await screen.findByText('Admissions dashboard')).toBeInTheDocument();
  });

  it('hides the dashboard from a signed-in user without the capability', () => {
    useAuthMock.value = {
      user: { id: 'u2', role: 'student', capabilities: [] },
      isLoading: false,
      can: () => false,
    };

    render(<AdmissionsDashboardPage />);
    expect(screen.queryByText('Admissions dashboard')).not.toBeInTheDocument();
    expect(screen.getByText(/do not have access/i)).toBeInTheDocument();
  });
});
