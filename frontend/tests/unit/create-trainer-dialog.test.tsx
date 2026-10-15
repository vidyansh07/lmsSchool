import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CreateTrainerDialog } from '@/app/admin/trainers/create-trainer-dialog';

const createTrainer = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, createTrainer };
});

vi.mock('@/components/organisation/branch-field', () => ({ BranchField: () => null }));

beforeEach(() => {
  createTrainer.mockReset();
  createTrainer.mockResolvedValue({});
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
