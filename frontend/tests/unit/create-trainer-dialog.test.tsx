import { render, screen, waitFor } from '@testing-library/react';
import { ApiError } from '@/lib/api';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CreateTrainerDialog } from '@/app/admin/trainers/create-trainer-dialog';

const createTrainer = vi.hoisted(() => vi.fn());
const listUsers = vi.hoisted(() => vi.fn());
const ensureTeachingProfile = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, createTrainer, listUsers, ensureTeachingProfile };
});
const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

vi.mock('@/components/organisation/branch-field', () => ({ BranchField: () => null }));

beforeEach(() => {
  createTrainer.mockReset();
  createTrainer.mockResolvedValue({});
  listUsers.mockReset();
  ensureTeachingProfile.mockReset();
  useAuth.mockReturnValue({ can: (capability: string) => capability === 'user.view_any' });
});

describe('CreateTrainerDialog', () => {
  it('creates the account and trainer profile through one request', async () => {
    const onCreated = vi.fn();
    const user = userEvent.setup();
    render(<CreateTrainerDialog open onClose={vi.fn()} onCreated={onCreated} />);

    await user.type(screen.getByLabelText(/^Email/), ' trainer@example.com ');
    await user.type(screen.getByLabelText(/^Phone/), '+919876543210');
    await user.type(screen.getByLabelText(/^First name/), ' Tina ');
    await user.type(screen.getByLabelText(/^Last name/), ' Trainer ');
    await user.type(screen.getByLabelText(/^Professional title/), ' Senior instructor ');
    await user.type(screen.getByLabelText(/^Skills/), 'Linux, Python');
    await user.type(screen.getByLabelText(/^Years of experience/), '6');
    await user.click(screen.getByRole('button', { name: 'Create trainer' }));

    await waitFor(() =>
      expect(createTrainer).toHaveBeenCalledWith({
        email: 'trainer@example.com',
        first_name: 'Tina',
        last_name: 'Trainer',
        phone: '+919876543210',
        profile: {
          professional_title: 'Senior instructor',
          skills: ['Linux', 'Python'],
          years_of_experience: 6,
        },
      }),
    );
    expect(onCreated).toHaveBeenCalledOnce();
    expect(screen.getByLabelText(/^Email/)).toHaveValue('');
  });

  it('protects entered details until discard is confirmed', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<CreateTrainerDialog open onClose={onClose} onCreated={vi.fn()} />);

    await user.type(screen.getByLabelText(/^Email/), 'trainer@example.com');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Discard this trainer?');
    await user.click(screen.getByRole('button', { name: 'Keep editing' }));
    expect(screen.getByLabelText(/^Email/)).toHaveValue('trainer@example.com');

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.getByLabelText(/^Email/)).toHaveValue('');
  });
});

describe('CreateTrainerDialog — an address that already has an account', () => {
  async function submitTaken(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText(/^Email/), 'meera@example.com');
    await user.type(screen.getByLabelText(/^First name/), 'Meera');
    await user.click(screen.getByRole('button', { name: 'Create trainer' }));
  }

  it('says whose it is and lets a manager teach without changing role', async () => {
    createTrainer.mockRejectedValue(
      new ApiError(400, 'validation_error', 'Invalid.', 'r', {
        email: ['An account with this email already exists.'],
      }),
    );
    listUsers.mockResolvedValue({
      count: 1,
      page: 1,
      page_size: 5,
      total_pages: 1,
      results: [
        {
          id: 'u-meera',
          email: 'meera@example.com',
          full_name: 'Meera Manager',
          role: 'manager',
          is_active: true,
          profile_type: null,
          profile_id: null,
        },
      ],
    });
    ensureTeachingProfile.mockResolvedValue({});
    const onCreated = vi.fn();
    const user = userEvent.setup();
    render(<CreateTrainerDialog open onClose={vi.fn()} onCreated={onCreated} />);
    await submitTaken(user);

    expect(await screen.findByText(/A manager can teach without changing role/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open account' })).toHaveAttribute('href', '/admin/users/u-meera');
    await user.click(screen.getByRole('button', { name: 'Let this manager teach' }));
    await waitFor(() => expect(ensureTeachingProfile).toHaveBeenCalledWith('u-meera'));
    expect(onCreated).toHaveBeenCalledOnce();
  });

  it('keeps the plain message for someone who cannot read accounts', async () => {
    useAuth.mockReturnValue({ can: () => false });
    createTrainer.mockRejectedValue(
      new ApiError(400, 'validation_error', 'Invalid.', 'r', {
        email: ['An account with this email already exists.'],
      }),
    );
    const user = userEvent.setup();
    render(<CreateTrainerDialog open onClose={vi.fn()} onCreated={vi.fn()} />);
    await submitTaken(user);

    expect(await screen.findByText('An account with this email already exists.')).toBeInTheDocument();
    expect(listUsers).not.toHaveBeenCalled();
  });
});
