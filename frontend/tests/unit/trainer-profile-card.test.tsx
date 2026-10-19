/**
 * The trainer's own page now says who they are and lets a manager correct it:
 * title, skills (as tags), experience and availability; whether the
 * invitation was ever accepted, with a resend; and a link to the account.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TrainerProfileCard } from '@/components/manage/trainer-profile-card';
import type { TrainerProfile } from '@/types/api';

const getTrainer = vi.hoisted(() => vi.fn());
const updateTrainer = vi.hoisted(() => vi.fn());
const bulkTrainers = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', () => ({ getTrainer, updateTrainer }));
vi.mock('@/lib/bulk', () => ({ bulkTrainers }));
const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

function profile(overrides: Partial<TrainerProfile> = {}): TrainerProfile {
  return {
    id: 'tp-1',
    trainer_id: 'GRS-T-001',
    user: {
      id: 'u-1',
      email: 'tina@example.com',
      first_name: 'Tina',
      last_name: 'Trainer',
      full_name: 'Tina Trainer',
      role: 'trainer',
      is_active: true,
      is_email_verified: false,
      invitation_accepted: false,
    } as TrainerProfile['user'],
    professional_title: 'Senior trainer',
    bio: '',
    skills: ['Linux'],
    expertise: '',
    qualifications: '',
    years_of_experience: 6,
    professional_links: {},
    is_accepting_assignments: true,
    completion_percent: 50,
    is_profile_complete: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    can: (capability: string) =>
      ['trainer.update_any', 'user.view_any', 'user.update_any'].includes(capability),
  });
});

describe('TrainerProfileCard', () => {
  it('says the invitation was never accepted and resends it', async () => {
    getTrainer.mockResolvedValue(profile());
    bulkTrainers.mockResolvedValue({ action: 'resend_invitation', total: 1, done: 1, skipped: [] });
    const user = userEvent.setup();
    render(<TrainerProfileCard trainerId="tp-1" />);

    expect(await screen.findByText('Invitation not accepted')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Account' })).toHaveAttribute('href', '/admin/users/u-1');
    await user.click(screen.getByRole('button', { name: 'Resend invitation' }));
    await waitFor(() =>
      expect(bulkTrainers).toHaveBeenCalledWith({ action: 'resend_invitation', ids: ['tp-1'] }),
    );
    expect(await screen.findByText(/new invitation to set a password went/i)).toBeInTheDocument();
  });

  it('says why the invitation could not be sent', async () => {
    getTrainer.mockResolvedValue(profile());
    bulkTrainers.mockResolvedValue({
      action: 'resend_invitation',
      total: 1,
      done: 0,
      skipped: [{ id: 'tp-1', label: 'Tina Trainer', reason: 'The email could not be sent: the mail service refused it.' }],
    });
    const user = userEvent.setup();
    render(<TrainerProfileCard trainerId="tp-1" />);
    await user.click(await screen.findByRole('button', { name: 'Resend invitation' }));
    expect(await screen.findByText(/could not be sent: the mail service refused it/)).toBeInTheDocument();
  });

  it('edits skills as tags and saves the profile', async () => {
    getTrainer.mockResolvedValue(profile({ user: { ...profile().user, is_email_verified: true } }));
    updateTrainer.mockImplementation(async (_id: string, changes: Partial<TrainerProfile>) => ({
      ...profile(),
      ...changes,
    }));
    const user = userEvent.setup();
    render(<TrainerProfileCard trainerId="tp-1" />);

    await user.click(await screen.findByRole('button', { name: 'Edit profile' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit trainer profile' });
    await user.type(within(dialog).getByLabelText(/^Skills/), 'Python{Enter}');
    await user.click(within(dialog).getByRole('button', { name: 'Remove Linux' }));
    await user.click(within(dialog).getByRole('button', { name: 'Save profile' }));

    await waitFor(() =>
      expect(updateTrainer).toHaveBeenCalledWith('tp-1', expect.objectContaining({ skills: ['Python'] })),
    );
    expect(await screen.findByText('Profile saved.')).toBeInTheDocument();
  });

  it('offers no editing to someone who only reads trainers', async () => {
    useAuth.mockReturnValue({ can: () => false });
    getTrainer.mockResolvedValue(profile());
    render(<TrainerProfileCard trainerId="tp-1" />);
    expect(await screen.findByText('Senior trainer')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit profile' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Resend invitation' })).toBeNull();
  });
});
