/**
 * New Student, step 1 — the admissions desk's own form.
 *
 * The behaviour worth pinning down is the three repeatable fields. The first
 * mobile and the first email are the student's *account*; everything else is
 * a contact row that can never sign anybody in. A test that only checked the
 * fields rendered would not catch the day that split inverts, which is the
 * one mistake here that would matter.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { NewStudentForm } from '@/app/students/new/page';
import { ApiError } from '@/lib/api';

const createStudent = vi.hoisted(() => vi.fn());
const listColleges = vi.hoisted(() => vi.fn());
const addCollege = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, createStudent, listColleges, addCollege };
});

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

const useApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi }));

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe('NewStudentForm', () => {
  beforeEach(() => {
    createStudent.mockReset().mockResolvedValue({ id: 'student-1' });
    listColleges.mockReset().mockResolvedValue({ count: 0, results: [] });
    addCollege.mockReset();
    push.mockReset();
    useApi.mockImplementation((path: string) => {
      if (path.startsWith('/api/v1/settings/public/')) {
        return { data: { institution_name: 'Grras Solutions Pvt. Ltd.' }, isLoading: false };
      }
      if (path.startsWith('/api/v1/users/')) {
        return {
          data: { results: [{ id: 'user-1', full_name: 'Deepti Vyas', email: 'd@x.test' }] },
          isLoading: false,
        };
      }
      return { data: null, isLoading: false, error: null, reload: vi.fn() };
    });
  });

  it('asks for what the desk asks for, in the order it asks', () => {
    render(<NewStudentForm />);

    expect(screen.getByRole('heading', { name: /New Student/ })).toBeInTheDocument();
    expect(screen.getByText('Grras Solutions Pvt. Ltd.', { exact: false })).toBeInTheDocument();
    for (const label of [
      'Picture',
      'Roll No.',
      'Name',
      'Gender',
      'Date of Birth',
      'Address',
      'Nationality',
      'Mobile',
      'Landline',
      'School/College',
      'Email',
      'Owner',
    ]) {
      // `getAllByText`: "Address" is both the row's label and the textarea's
      // own accessible name, which is correct and would fail a single-match
      // query.
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByPlaceholderText('Enter roll number')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Firstname')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Middlename')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Lastname')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('shows the five steps, with the ones ahead not yet openable', () => {
    render(<NewStudentForm />);
    const bar = screen.getByRole('list', { name: 'Registration steps' });
    expect(within(bar).getByRole('button', { name: '1. Student Details' })).toHaveAttribute(
      'aria-current',
      'step',
    );
    expect(within(bar).getByRole('button', { name: '2. Guardian Details' })).toBeDisabled();
    expect(within(bar).getByRole('button', { name: '5. Batch Details' })).toBeDisabled();
  });

  it('keeps the tips the original carries', () => {
    render(<NewStudentForm />);
    expect(screen.getByText(/send payment reminder, exam result updates via sms/)).toBeInTheDocument();
    expect(screen.getByText(/to send exam results via email/)).toBeInTheDocument();
  });

  it('sends the primary mobile and email as the account, and the rest as contacts', async () => {
    render(<NewStudentForm />);

    fireEvent.change(screen.getByPlaceholderText('Firstname'), { target: { value: 'Ravi' } });
    fireEvent.change(screen.getByPlaceholderText('Middlename'), { target: { value: 'Kumar' } });
    fireEvent.change(screen.getByPlaceholderText('Lastname'), { target: { value: 'Sharma' } });
    fill('Mobile number 1', '9876543210');
    fill('Email 1', 'ravi@example.test');

    fireEvent.click(screen.getByRole('button', { name: 'Add another mobile number' }));
    fill('Mobile number 2', '9829012345');
    fireEvent.click(screen.getByRole('button', { name: 'Add another email' }));
    fill('Email 2', 'ravi.home@example.test');
    fill('STD code 1', '0141');
    fill('Landline number 1', '2345678');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(createStudent).toHaveBeenCalled());
    const payload = createStudent.mock.calls[0]![0];
    expect(payload.email).toBe('ravi@example.test');
    expect(payload.middle_name).toBe('Kumar');
    expect(payload.contacts).toEqual([
      { kind: 'mobile', code: '+91', value: '9829012345' },
      { kind: 'landline', code: '0141', value: '2345678' },
      { kind: 'email', value: 'ravi.home@example.test' },
    ]);
    expect(push).toHaveBeenCalledWith('/students/student-1/guardians?new=1');
  });

  it('follows the tick: the marked row becomes the account, the other the contact', async () => {
    render(<NewStudentForm />);
    fireEvent.change(screen.getByPlaceholderText('Firstname'), { target: { value: 'Ravi' } });
    fill('Email 1', 'first@example.test');
    fireEvent.click(screen.getByRole('button', { name: 'Add another email' }));
    fill('Email 2', 'second@example.test');

    // Mark the second one primary. Two primaries is not a state that means
    // anything, so these behave as radios however the original draws them.
    const primaries = screen.getAllByRole('radio', { name: 'Primary' });
    fireEvent.click(primaries[primaries.length - 1]!);

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(createStudent).toHaveBeenCalled());
    const payload = createStudent.mock.calls[0]![0];
    expect(payload.email).toBe('second@example.test');
    expect(payload.contacts).toEqual([{ kind: 'email', value: 'first@example.test' }]);
  });

  it('will not save without a name or an email, and says which', async () => {
    render(<NewStudentForm />);
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Enter the first name.')).toBeInTheDocument();
    expect(screen.getByText(/An email is needed/)).toBeInTheDocument();
    expect(createStudent).not.toHaveBeenCalled();
  });

  it('refuses half a date of birth rather than sending a wrong one', async () => {
    render(<NewStudentForm />);
    fireEvent.change(screen.getByPlaceholderText('Firstname'), { target: { value: 'Ravi' } });
    fill('Email 1', 'ravi@example.test');
    fireEvent.change(screen.getByLabelText('Day'), { target: { value: '7' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(
      await screen.findByText('Give the whole date, or leave all three blank.'),
    ).toBeInTheDocument();
    expect(createStudent).not.toHaveBeenCalled();
  });

  it('sends a whole date of birth as one value', async () => {
    render(<NewStudentForm />);
    fireEvent.change(screen.getByPlaceholderText('Firstname'), { target: { value: 'Ravi' } });
    fill('Email 1', 'ravi@example.test');
    fireEvent.change(screen.getByLabelText('Day'), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText('Month'), { target: { value: 'March' } });
    fireEvent.change(screen.getByLabelText('Year'), { target: { value: '2004' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(createStudent).toHaveBeenCalled());
    expect(createStudent.mock.calls[0]![0].profile.date_of_birth).toBe('2004-03-07');
  });

  it('never drops to zero rows when the last one is removed', () => {
    render(<NewStudentForm />);
    fill('Mobile number 1', '9876543210');
    fireEvent.click(screen.getByRole('button', { name: 'Remove mobile number 1' }));
    // Still one row, and empty — there is no "add another" to click back from
    // an empty field.
    expect(screen.getByLabelText('Mobile number 1')).toHaveValue('');
    expect(screen.queryByLabelText('Mobile number 2')).not.toBeInTheDocument();
  });

  it('shows what the server said when it refuses the registration', async () => {
    createStudent.mockRejectedValue(
      new ApiError(400, 'validation_error', 'Could not register.', 'req-1', {
        email: ['An account with this email already exists.'],
      }),
    );
    render(<NewStudentForm />);
    fireEvent.change(screen.getByPlaceholderText('Firstname'), { target: { value: 'Ravi' } });
    fill('Email 1', 'taken@example.test');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(
      await screen.findByText('An account with this email already exists.'),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
