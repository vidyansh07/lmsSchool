/**
 * The placement desk (`/placement`): the figures it opens with, who is still
 * looking, the offer list and its filter, and recording or editing an offer.
 *
 * What the capability tests here are about: the page is opened by
 * `placement.view_any` and *written* by `placement.manage`, and a role may
 * hold the first without the second. Hiding the write buttons is a courtesy
 * — the server refuses the request either way — but a read-only placement
 * officer should not be offered a button that will 403.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PlacementWorkspace } from '@/app/placement/page';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import type { Paginated, Placement, PlacementSummary, StudentListRow } from '@/types/api';

const listPlacements = vi.hoisted(() => vi.fn());
const placementSummary = vi.hoisted(() => vi.fn());
const recordPlacement = vi.hoisted(() => vi.fn());
const updatePlacement = vi.hoisted(() => vi.fn());
vi.mock('@/lib/placements', () => ({
  listPlacements,
  placementSummary,
  recordPlacement,
  updatePlacement,
}));

const listStudents = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, listStudents };
});

const allowed = vi.hoisted(() => ({ value: new Set<string>() }));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ can: (capability: string) => allowed.value.has(capability) }),
}));

function page<T>(results: T[]): Paginated<T> {
  return { count: results.length, page: 1, page_size: 50, total_pages: 1, next: null, previous: null, results };
}

function placement(overrides: Partial<Placement> = {}): Placement {
  return {
    id: 'placement-1',
    student_id: 'student-1',
    student_name: 'Asha Rao',
    student_code: 'GRS-S-00001',
    enrollment_id: null,
    course_title: null,
    branch_id: 'branch-1',
    branch_name: 'Jaipur corporate',
    company: 'Infosys',
    role_title: 'Associate Engineer',
    location: 'Bengaluru',
    status: 'offered',
    is_placed: false,
    annual_package: '450000.00',
    offered_on: '2026-09-01',
    joined_on: null,
    notes: '',
    recorded_by: 'Kiran Counsellor',
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
    ...overrides,
  };
}

const SUMMARY: PlacementSummary = {
  offers: 7,
  open_offers: 3,
  closed_offers: 2,
  placed_students: 2,
  offers_this_month: 4,
};

function student(): StudentListRow {
  return {
    id: 'student-9',
    student_id: 'GRS-S-00009',
    user_id: 'user-9',
    email: 'ravi@example.test',
    full_name: 'Ravi Sharma',
    city: 'Jaipur',
    qualification: 'bachelors',
    fee_status: 'paid',
    fee_amount: null,
    fee_payable: '0.00',
    fee_paid: '0.00',
    fee_balance: '0.00',
    fee_next_due_on: null,
    institution: 'Arya College',
    roll_number: '',
    institution_kind: 'college',
    referred_by: null,
    is_active: true,
  } as StudentListRow;
}

describe('PlacementWorkspace', () => {
  beforeEach(() => {
    allowed.value = new Set<string>(Object.values(Capability));
    listPlacements.mockReset().mockResolvedValue(page([placement()]));
    placementSummary.mockReset().mockResolvedValue(SUMMARY);
    recordPlacement.mockReset().mockResolvedValue(placement());
    updatePlacement.mockReset().mockResolvedValue(placement());
    listStudents.mockReset().mockResolvedValue(page([student()]));
  });

  it('opens with the desk figures, naming what each one counts', async () => {
    render(<PlacementWorkspace />);

    expect(await screen.findByText('Students placed')).toBeInTheDocument();
    expect(screen.getByText('Accepted or joined. Counts people, not offers.')).toBeInTheDocument();
    expect(screen.getByText('Offers still open')).toBeInTheDocument();
    expect(await screen.findByText('2 declined or withdrawn')).toBeInTheDocument();
  });

  it('lists the offers with the company, status and package', async () => {
    render(<PlacementWorkspace />);

    expect(await screen.findByText('Infosys')).toBeInTheDocument();
    expect(screen.getByText('Associate Engineer')).toBeInTheDocument();
    expect(screen.getByText('Offered')).toBeInTheDocument();
    expect(screen.getByText('₹4,50,000')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Asha Rao' })).toHaveAttribute(
      'href',
      '/students/student-1',
    );
  });

  it('says so rather than showing a zero when a package has not been stated', async () => {
    listPlacements.mockResolvedValue(page([placement({ annual_package: null })]));
    render(<PlacementWorkspace />);

    expect(await screen.findByText('Infosys')).toBeInTheDocument();
    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(screen.queryByText('₹0')).not.toBeInTheDocument();
  });

  it('narrows the list to the offers that became a job', async () => {
    render(<PlacementWorkspace />);
    await screen.findByText('Infosys');

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'placed' } });

    await waitFor(() =>
      expect(listPlacements).toHaveBeenCalledWith({ placed: true, page_size: 50 }),
    );
  });

  it('narrows the list to one status', async () => {
    render(<PlacementWorkspace />);
    await screen.findByText('Infosys');

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'declined' } });

    await waitFor(() =>
      expect(listPlacements).toHaveBeenCalledWith({ status: 'declined', page_size: 50 }),
    );
  });

  it('shows who said they are open to placement, as the student’s own answer', async () => {
    render(<PlacementWorkspace />);

    expect(await screen.findByText('Still looking')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ravi Sharma' })).toHaveAttribute(
      'href',
      '/students/student-9',
    );
    expect(listStudents).toHaveBeenCalledWith({ open_to_placement: 'true', page_size: 10 });
  });

  it('records an offer and reloads the figures with it', async () => {
    render(<PlacementWorkspace />);
    await screen.findByText('Infosys');

    fireEvent.click(screen.getByRole('button', { name: /Record an offer/i }));
    fireEvent.change(screen.getByLabelText('Company'), { target: { value: 'TCS' } });
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'Engineer' } });
    fireEvent.change(screen.getByLabelText('Offered on'), { target: { value: '2026-10-01' } });

    // No student chosen yet: the form says so rather than sending a request
    // the server will refuse.
    fireEvent.click(screen.getByRole('button', { name: 'Record offer' }));
    expect(await screen.findByText('Choose the student this offer is for.')).toBeInTheDocument();
    expect(recordPlacement).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Student'), { target: { value: 'Ravi' } });
    const option = await screen.findByRole('button', { name: /Ravi Sharma/ });
    fireEvent.click(option);
    fireEvent.click(screen.getByRole('button', { name: 'Record offer' }));

    await waitFor(() =>
      expect(recordPlacement).toHaveBeenCalledWith({
        student: 'student-9',
        company: 'TCS',
        role_title: 'Engineer',
        location: '',
        status: 'offered',
        annual_package: null,
        offered_on: '2026-10-01',
        joined_on: null,
        notes: '',
      }),
    );
    await waitFor(() => expect(placementSummary).toHaveBeenCalledTimes(2));
  });

  it('refuses to mark an offer joined without the date they joined', async () => {
    render(<PlacementWorkspace />);
    await screen.findByText('Infosys');

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'joined' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByText('Say when they joined.')).toBeInTheDocument();
    expect(updatePlacement).not.toHaveBeenCalled();
  });

  it('refuses a joining date on an offer that was declined', async () => {
    render(<PlacementWorkspace />);
    await screen.findByText('Infosys');

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'declined' } });
    fireEvent.change(screen.getByLabelText('Joined on'), { target: { value: '2026-10-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    expect(
      await screen.findByText('An offer that was declined or withdrawn has no joining date.'),
    ).toBeInTheDocument();
    expect(updatePlacement).not.toHaveBeenCalled();
  });

  it('moves an offer along, keeping the student it was recorded against', async () => {
    render(<PlacementWorkspace />);
    await screen.findByText('Infosys');

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    // Editing offers no student field at all: an offer against the wrong
    // person is withdrawn and recorded again, so the first student's record
    // keeps its history.
    expect(screen.queryByLabelText('Student')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'joined' } });
    fireEvent.change(screen.getByLabelText('Joined on'), { target: { value: '2026-10-15' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() =>
      expect(updatePlacement).toHaveBeenCalledWith(
        'placement-1',
        expect.objectContaining({ status: 'joined', joined_on: '2026-10-15' }),
      ),
    );
  });

  it('offers nothing that writes to a read-only placement officer', async () => {
    allowed.value = new Set([Capability.placementViewAny, Capability.studentViewAny]);
    render(<PlacementWorkspace />);

    expect(await screen.findByText('Infosys')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Record an offer/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
  });

  it('leaves out the "still looking" list for a role that may not read students', async () => {
    allowed.value = new Set([Capability.placementViewAny, Capability.placementManage]);
    render(<PlacementWorkspace />);

    expect(await screen.findByText('Infosys')).toBeInTheDocument();
    expect(screen.queryByText('Still looking')).not.toBeInTheDocument();
    expect(listStudents).not.toHaveBeenCalled();
  });

  it('keeps the figures when the offer list fails, and offers a retry', async () => {
    listPlacements.mockRejectedValue(new ApiError(500, 'server_error', 'Offers are down.', 'req-1'));
    render(<PlacementWorkspace />);

    expect(await screen.findByText('Students placed')).toBeInTheDocument();
    expect(await screen.findByText('Offers are down.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(listPlacements).toHaveBeenCalledTimes(2));
  });

  it('says plainly when nobody has asked to be put forward', async () => {
    listStudents.mockResolvedValue(page([] as StudentListRow[]));
    render(<PlacementWorkspace />);

    expect(
      await screen.findByText(/Nobody has said they are open to placement yet/),
    ).toBeInTheDocument();
  });

  it('says plainly when no offer has been recorded', async () => {
    listPlacements.mockResolvedValue(page([] as Placement[]));
    render(<PlacementWorkspace />);

    expect(await screen.findByText('No offers recorded')).toBeInTheDocument();
  });

  it('names the package column once, for a screen reader reading the table', async () => {
    render(<PlacementWorkspace />);
    const table = await screen.findByRole('table');
    expect(within(table).getByText('Package')).toBeInTheDocument();
  });
});
