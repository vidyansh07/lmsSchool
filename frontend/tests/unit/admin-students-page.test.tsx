/**
 * `/admin/students` — migrated onto `DataTable` (Phase R6). Covers what the
 * migration must not have changed: every column renders real data, sort
 * still calls `listStudents` with the same query shape, the fee-status
 * select still drives the same real mutation it did before, and the density
 * toggle persists.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminStudentsPage from '@/app/admin/students/page';
import { ApiError } from '@/lib/api';
import type { StudentListRow } from '@/types/api';

const listStudents = vi.hoisted(() => vi.fn());
const setFeeStatus = vi.hoisted(() => vi.fn());
// Saved views load from the server; these tests are about the list itself.
vi.mock('@/lib/saved-filters', () => ({
  listSavedFilters: vi.fn().mockResolvedValue([]),
  createSavedFilter: vi.fn(),
  deleteSavedFilter: vi.fn(),
}));
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, listStudents, setFeeStatus };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));

const exportSelected = vi.hoisted(() => ({ value: undefined as readonly string[] | undefined }));
vi.mock('@/components/export-menu', () => ({
  ExportMenu: ({ selectedIds }: { selectedIds?: readonly string[] }) => {
    if (selectedIds) exportSelected.value = selectedIds;
    return null;
  },
}));
const bulkStudents = vi.hoisted(() => vi.fn());
vi.mock('@/lib/bulk', async () => {
  const actual = await vi.importActual<typeof import('@/lib/bulk')>('@/lib/bulk');
  return { ...actual, bulkStudents };
});
vi.mock('@/app/admin/students/create-student-dialog', () => ({ CreateStudentDialog: () => null }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

function page(results: StudentListRow[]) {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function studentRow(overrides: Partial<StudentListRow> = {}): StudentListRow {
  return {
    id: 's-1',
    student_id: 'GRS-S-001',
    user_id: 'u-1',
    email: 'asha@example.com',
    full_name: 'Asha Rao',
    city: 'Jaipur',
    qualification: 'bachelors',
    fee_status: 'partial',
    fee_amount: '30000.00',
    fee_payable: '30000.00',
    fee_paid: '10000.00',
    fee_balance: '20000.00',
    fee_next_due_on: '2026-10-01',
    institution: 'MNIT',
    roll_number: '',
    institution_kind: 'college',
    referred_by: null,
    is_active: true,
    is_email_verified: true,
    invitation_accepted: true,
    created_at: '2026-01-01',
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    user: { id: 'u-admin', role: 'admin', capabilities: ['student.view_any', 'student.set_fee_status'] },
    isLoading: false,
    can: (capability: string) =>
      capability === 'student.view_any' || capability === 'student.set_fee_status',
  });
});

describe('AdminStudentsPage', () => {
  it('renders every column with real data', async () => {
    listStudents.mockResolvedValue(page([studentRow()]));
    render(<AdminStudentsPage />);
    await waitFor(() => expect(screen.getByText('Asha Rao')).toBeInTheDocument());
    expect(screen.getByText('GRS-S-001')).toBeInTheDocument();
    expect(screen.getByText('asha@example.com')).toBeInTheDocument();
    expect(screen.getByText('Jaipur')).toBeInTheDocument();
    expect(screen.getByText('₹30,000')).toBeInTheDocument();
    expect(screen.getByText('₹20,000')).toBeInTheDocument();
  });

  it('renders a placeholder account — blank name and email, a qualification outside the enum — without throwing', async () => {
    listStudents.mockResolvedValue(
      page([
        studentRow({
          full_name: '',
          email: '',
          qualification: 'b_tech_2019' as StudentListRow['qualification'],
        }),
      ]),
    );
    render(<AdminStudentsPage />);
    await waitFor(() => expect(screen.getByText('GRS-S-001')).toBeInTheDocument());
    expect(screen.getByText('?')).toBeInTheDocument();
    expect(screen.getByText('B Tech 2019')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/undefined/);
  });

  it('sends the same sort field on the same server request', async () => {
    listStudents.mockResolvedValue(page([studentRow()]));
    render(<AdminStudentsPage />);
    await waitFor(() => expect(screen.getByText('Asha Rao')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /^id$/i }));
    await waitFor(() =>
      expect(listStudents).toHaveBeenLastCalledWith(
        expect.objectContaining({ ordering: 'student_id' }),
        expect.anything(),
      ),
    );
  });

  it('changes the fee status through the same real mutation as before', async () => {
    listStudents.mockResolvedValue(page([studentRow({ fee_status: 'partial' })]));
    setFeeStatus.mockResolvedValue({});
    render(<AdminStudentsPage />);
    await waitFor(() => expect(screen.getByText('Asha Rao')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText('Fee status for GRS-S-001'), 'paid');
    await waitFor(() => expect(setFeeStatus).toHaveBeenCalledWith('s-1', 'paid'));
  });

  it('shows an error with retry on failure', async () => {
    listStudents.mockRejectedValue(new ApiError(500, 'server_error', 'Could not load.', 'req-1'));
    render(<AdminStudentsPage />);
    await waitFor(() => expect(screen.getByText('Could not load students')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('persists the density toggle across a re-render', async () => {
    listStudents.mockResolvedValue(page([studentRow()]));
    const { unmount } = render(<AdminStudentsPage />);
    await waitFor(() => expect(screen.getByText('Asha Rao')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /compact view/i }));
    expect(window.localStorage.getItem('grras.admin-students-density')).toBe('compact');
    unmount();

    render(<AdminStudentsPage />);
    await waitFor(() => expect(screen.getByText('Asha Rao')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /comfortable view/i })).toBeInTheDocument();
  });
});

describe('AdminStudentsPage — acting on many students', () => {
  it('exports the ticked students and resends their invitations', async () => {
    useAuth.mockReturnValue({
      user: { id: 'u-admin', role: 'admin' },
      isLoading: false,
      can: () => true,
    });
    listStudents.mockResolvedValue(
      page([studentRow(), studentRow({ id: 's-2', full_name: 'Bala K', email: 'bala@example.com' })]),
    );
    bulkStudents.mockResolvedValue({ action: 'resend_invitation', total: 2, done: 2, skipped: [] });
    const user = userEvent.setup();
    render(<AdminStudentsPage />);

    await user.click(await screen.findByRole('checkbox', { name: 'Select Asha Rao' }));
    await user.click(screen.getByRole('checkbox', { name: 'Select Bala K' }));
    expect(exportSelected.value).toEqual(['s-1', 's-2']);

    await user.click(screen.getByRole('button', { name: 'Resend invitations' }));
    await user.click(screen.getByRole('button', { name: 'Send invitations' }));
    await waitFor(() =>
      expect(bulkStudents).toHaveBeenCalledWith({ ids: ['s-1', 's-2'], action: 'resend_invitation' }),
    );
    expect(await screen.findByRole('dialog', { name: 'Invitations' })).toHaveTextContent(
      '2 students invited again.',
    );
  });
});

describe('AdminStudentsPage — arriving from "Has referred N students"', () => {
  it('opens filtered to the students that student referred, and says so', async () => {
    window.history.replaceState(null, '', '/admin/students?referred_by=s-9');
    listStudents.mockResolvedValue(page([studentRow()]));
    render(<AdminStudentsPage />);

    await waitFor(() =>
      expect(listStudents).toHaveBeenCalledWith(
        expect.objectContaining({ referred_by: 's-9' }),
        expect.anything(),
      ),
    );
    expect(
      await screen.findByRole('button', { name: 'Remove filter Referred by: the student you came from' }),
    ).toBeInTheDocument();
    window.history.replaceState(null, '', '/');
  });
});
