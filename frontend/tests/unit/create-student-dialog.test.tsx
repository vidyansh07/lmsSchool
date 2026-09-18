/**
 * `CreateStudentDialog` (`app/admin/students/create-student-dialog.tsx`) —
 * Phase R7's Target 1. Coverage is specifically the new on-blur validation:
 * it must not change which fields are required (still only Email/First
 * name, per `Field`'s own `required` prop usage) and the existing
 * on-submit → server `fieldErrors(cause)` path must still work exactly as
 * before, unreplaced by the new client-side check.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CreateStudentDialog } from '@/app/admin/students/create-student-dialog';
import { ApiError } from '@/lib/api';

const createStudent = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', () => ({ createStudent }));

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

beforeEach(() => {
  vi.clearAllMocks();
  // A bounded (non-superadmin) account: `BranchField` renders nothing for
  // one, same as every other test that mounts a form containing it — kept
  // out of scope for this phase's target.
  useAuth.mockReturnValue({ user: { id: 'u-admin', role: 'admin', branch_id: 'b-1' } });
});

describe('CreateStudentDialog — on-blur validation', () => {
  it('shows a required message for Email on blur, before any submit', async () => {
    render(<CreateStudentDialog onClose={vi.fn()} onCreated={vi.fn()} />);
    const email = screen.getByLabelText(/^Email/);
    fireEvent.focus(email);
    fireEvent.blur(email);
    expect(await screen.findByText('Email is required.')).toBeInTheDocument();
    expect(createStudent).not.toHaveBeenCalled();
  });

  it('shows a required message for First name on blur', async () => {
    render(<CreateStudentDialog onClose={vi.fn()} onCreated={vi.fn()} />);
    const firstName = screen.getByLabelText(/^First name/);
    fireEvent.focus(firstName);
    fireEvent.blur(firstName);
    expect(await screen.findByText('First name is required.')).toBeInTheDocument();
  });

  it('flags an obviously malformed email on blur', async () => {
    render(<CreateStudentDialog onClose={vi.fn()} onCreated={vi.fn()} />);
    const email = screen.getByLabelText(/^Email/);
    fireEvent.change(email, { target: { value: 'not-an-email' } });
    fireEvent.blur(email);
    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument();
  });

  it('clears the on-blur message once the field is fixed', async () => {
    render(<CreateStudentDialog onClose={vi.fn()} onCreated={vi.fn()} />);
    const email = screen.getByLabelText(/^Email/);
    fireEvent.blur(email);
    expect(await screen.findByText('Email is required.')).toBeInTheDocument();

    fireEvent.change(email, { target: { value: 'asha@example.com' } });
    fireEvent.blur(email);
    await waitFor(() => expect(screen.queryByText('Email is required.')).not.toBeInTheDocument());
  });

  it('never adds a blur message for a field the form does not mark required', async () => {
    render(<CreateStudentDialog onClose={vi.fn()} onCreated={vi.fn()} />);
    const phone = screen.getByLabelText(/^Phone/);
    fireEvent.focus(phone);
    fireEvent.blur(phone);
    // Phone carries no `required` prop today (a backend-contract question,
    // out of this phase's scope) — blur must not invent a new requirement.
    expect(screen.queryByText(/is required/)).not.toBeInTheDocument();
  });

  it('still runs the unchanged on-submit path: server errors populate fieldErrors exactly as before', async () => {
    createStudent.mockRejectedValue(
      new ApiError(400, 'validation_error', 'The submitted data is invalid.', 'req-1', {
        email: ['A student with this email already exists.'],
      }),
    );
    render(<CreateStudentDialog onClose={vi.fn()} onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'asha@example.com' } });
    fireEvent.change(screen.getByLabelText(/^First name/), { target: { value: 'Asha' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create student' }));

    expect(
      await screen.findByText('A student with this email already exists.'),
    ).toBeInTheDocument();
    expect(createStudent).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'asha@example.com', first_name: 'Asha' }),
    );
  });

  it('still creates the student and calls onCreated on a successful submit, unaffected by on-blur validation', async () => {
    const onCreated = vi.fn();
    createStudent.mockResolvedValue({ id: 's-1' });
    render(<CreateStudentDialog onClose={vi.fn()} onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'asha@example.com' } });
    fireEvent.blur(screen.getByLabelText(/^Email/));
    fireEvent.change(screen.getByLabelText(/^First name/), { target: { value: 'Asha' } });
    fireEvent.blur(screen.getByLabelText(/^First name/));
    expect(screen.queryByText(/is required/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Create student' }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });
});
