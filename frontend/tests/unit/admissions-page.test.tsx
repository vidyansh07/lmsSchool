/**
 * `/admissions` — migrated onto `DataTable` (Phase R6). Covers what the
 * migration must not have changed: every column renders real data, sort
 * still calls `listEnrollments` with the same query shape, the client-side
 * registration-date narrowing (the API cannot filter by it) still applies
 * only to the current page's rows, and the density toggle persists.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdmissionsPage from '@/app/admissions/page';
import { ApiError } from '@/lib/api';
import type { Enrollment } from '@/types/api';

const listEnrollments = vi.hoisted(() => vi.fn());
const listBatches = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, listEnrollments, listBatches };
});

const listCourses = vi.hoisted(() => vi.fn());
vi.mock('@/lib/courses', async () => {
  const actual = await vi.importActual<typeof import('@/lib/courses')>('@/lib/courses');
  return { ...actual, listCourses };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));
vi.mock('@/components/export-menu', () => ({ ExportMenu: () => null }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

function page(results: Enrollment[]) {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function enrollmentRow(overrides: Partial<Enrollment> = {}): Enrollment {
  return {
    id: 'e-1',
    code: 'GRS-E-001',
    course_id: 'c-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    batch_id: 'b-1',
    batch_code: 'GRS-B-001',
    batch_name: 'Morning Linux batch',
    batch_status: 'active',
    trainer_name: 'Tina Trainer',
    status: 'active',
    enrolled_at: '2026-09-10T09:00:00Z',
    start_date: '2026-09-10',
    access_end_date: null,
    completed_at: null,
    grants_access: true,
    student_id: 's-1',
    student_code: 'GRS-S-001',
    student_name: 'Asha Rao',
    student_email: 'asha@example.com',
    fee_payable: '30000.00',
    fee_paid: '10000.00',
    fee_balance: '20000.00',
    fee_next_due_on: '2026-10-01',
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    user: { id: 'u-counsellor', role: 'counsellor', capabilities: ['enrolment.view_any'] },
    isLoading: false,
    can: (capability: string) => capability === 'enrolment.view_any',
  });
  listCourses.mockResolvedValue({ count: 0, page: 1, page_size: 100, total_pages: 1, next: null, previous: null, results: [] });
  listBatches.mockResolvedValue({ count: 0, page: 1, page_size: 100, total_pages: 1, next: null, previous: null, results: [] });
});

describe('AdmissionsPage', () => {
  it('renders every column with real data', async () => {
    listEnrollments.mockResolvedValue(page([enrollmentRow()]));
    render(<AdmissionsPage />);
    await waitFor(() => expect(screen.getByText('Asha Rao')).toBeInTheDocument());
    expect(screen.getByText('Linux Essentials')).toBeInTheDocument();
    expect(screen.getByText('Morning Linux batch')).toBeInTheDocument();
    expect(screen.getByText('Tina Trainer')).toBeInTheDocument();
    expect(screen.getByText(/due/)).toBeInTheDocument();
  });

  it('sends the same sort field on the same server request', async () => {
    listEnrollments.mockResolvedValue(page([enrollmentRow()]));
    render(<AdmissionsPage />);
    await waitFor(() => expect(screen.getByText('Asha Rao')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /registered/i }));
    await waitFor(() =>
      expect(listEnrollments).toHaveBeenLastCalledWith(
        expect.objectContaining({ ordering: 'enrolled_at' }),
        expect.anything(),
      ),
    );
  });

  it('narrows to the current page by registration date without a new server request', async () => {
    listEnrollments.mockResolvedValue(
      page([
        enrollmentRow({ id: 'e-old', enrolled_at: '2026-01-01T00:00:00Z', student_name: 'Old Student' }),
        enrollmentRow({ id: 'e-new', enrolled_at: '2026-09-10T00:00:00Z', student_name: 'Asha Rao' }),
      ]),
    );
    render(<AdmissionsPage />);
    await waitFor(() => expect(screen.getByText('Old Student')).toBeInTheDocument());
    const callsBefore = listEnrollments.mock.calls.length;

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Registered from'), '2026-09-01');

    await waitFor(() => expect(screen.queryByText('Old Student')).not.toBeInTheDocument());
    expect(screen.getByText('Asha Rao')).toBeInTheDocument();
    // The date range is not a real query param — it only narrows what is
    // already on screen, so no new fetch happens for it.
    expect(listEnrollments.mock.calls.length).toBe(callsBefore);
  });

  it('shows an error with retry on failure', async () => {
    listEnrollments.mockRejectedValue(new ApiError(500, 'server_error', 'Could not load.', 'req-1'));
    render(<AdmissionsPage />);
    await waitFor(() => expect(screen.getByText('Could not load admissions')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('persists the density toggle across a re-render', async () => {
    listEnrollments.mockResolvedValue(page([enrollmentRow()]));
    const { unmount } = render(<AdmissionsPage />);
    await waitFor(() => expect(screen.getByText('Asha Rao')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /compact view/i }));
    expect(window.localStorage.getItem('grras.admissions-density')).toBe('compact');
    unmount();

    render(<AdmissionsPage />);
    await waitFor(() => expect(screen.getByText('Asha Rao')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /comfortable view/i })).toBeInTheDocument();
  });
});
