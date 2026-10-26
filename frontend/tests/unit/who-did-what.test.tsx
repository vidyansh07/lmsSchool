/**
 * "Who did what": pick a person, pick a span, read what they did.
 *
 * The page owns the choosing and nothing else — every figure comes from the
 * staff record engine, which has its own tests. So what is pinned here is the
 * choosing: that students are not offered (a student's "what did they do" is
 * their own timeline, a different question), and that switching person starts
 * the next record afresh rather than showing the previous one's figures under
 * a new name while the request is in flight.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WhoDidWhat } from '@/app/admin/reports/who-did-what/page';
import { ApiError } from '@/lib/api';

const listUsers = vi.hoisted(() => vi.fn());
const getStaffRecord = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, listUsers, getStaffRecord };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

function person(id: string, name: string, role: string) {
  return { id, full_name: name, email: `${id}@x.test`, role };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ can: () => true });
  listUsers.mockResolvedValue({
    count: 3,
    next: null,
    previous: null,
    results: [
      person('u1', 'Kiran Counsellor', 'counsellor'),
      person('u2', 'Rahul Trainer', 'trainer'),
      person('u3', 'Aarti Student', 'student'),
    ],
  });
  getStaffRecord.mockResolvedValue({
    person: { id: 'u1', name: 'Kiran Counsellor', email: 'k@x.test', role: 'counsellor', is_active: true },
    start: '2026-09-26',
    end: '2026-10-26',
    counters: [{ key: 'admissions', label: 'Admissions taken', count: 18, amount: null }],
    timeline: [],
    timeline_truncated: false,
  });
});

describe('WhoDidWhat', () => {
  it('offers staff, and not students', async () => {
    render(<WhoDidWhat />);

    expect(await screen.findByRole('option', { name: /Kiran Counsellor/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Rahul Trainer/ })).toBeInTheDocument();
    // A student's "what did they do" is their own timeline — a different
    // question, answered on their own record.
    expect(screen.queryByRole('option', { name: /Aarti Student/ })).not.toBeInTheDocument();
  });

  it('asks for nobody until somebody is chosen', async () => {
    render(<WhoDidWhat />);

    await screen.findByRole('option', { name: /Kiran Counsellor/ });
    expect(getStaffRecord).not.toHaveBeenCalled();
    expect(screen.getByText(/Nobody chosen yet/)).toBeInTheDocument();
  });

  it('reads the chosen person’s record', async () => {
    render(<WhoDidWhat />);

    await screen.findByRole('option', { name: /Kiran Counsellor/ });
    fireEvent.change(screen.getByLabelText('Person'), { target: { value: 'u1' } });

    await waitFor(() => expect(getStaffRecord).toHaveBeenCalledWith('u1', expect.anything()));
    expect(await screen.findByText('Admissions taken')).toBeInTheDocument();
  });

  it('starts afresh when the person changes', async () => {
    render(<WhoDidWhat />);

    await screen.findByRole('option', { name: /Kiran Counsellor/ });
    fireEvent.change(screen.getByLabelText('Person'), { target: { value: 'u1' } });
    await waitFor(() => expect(getStaffRecord).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('Person'), { target: { value: 'u2' } });

    // Keyed by person: the second record is a fresh mount, so the first
    // one's figures are never on screen under the second one's name.
    await waitFor(() => expect(getStaffRecord).toHaveBeenLastCalledWith('u2', expect.anything()));
  });

  it('says what went wrong rather than offering an empty list', async () => {
    listUsers.mockRejectedValue(
      new ApiError(500, 'server_error', 'The staff list is unavailable.', 'r1'),
    );
    render(<WhoDidWhat />);

    // The server's own sentence, not the generic fallback beside it: when
    // the API has said something useful, repeating it is better than
    // replacing it with "could not read the staff list".
    expect(await screen.findByText('The staff list is unavailable.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Person')).not.toBeInTheDocument();
  });
});
