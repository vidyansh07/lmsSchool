import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TrainersHub } from '@/app/manage/trainers/page';
import { ApiError } from '@/lib/api';
import type { ManageTrainerRow } from '@/lib/manage';

const listManageTrainers = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, listManageTrainers };
});

vi.mock('@/components/manage/attention-strip', () => ({ ManagerAttentionStrip: () => null }));

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

function page(results: ManageTrainerRow[]) {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function trainerRow(overrides: Partial<ManageTrainerRow> = {}): ManageTrainerRow {
  return {
    id: 'trainer-1',
    trainer_id: 'GRS-T-001',
    user_id: 'u-trainer-1',
    email: 'tina@example.com',
    full_name: 'Tina Trainer',
    professional_title: 'Senior trainer',
    skills: ['Linux', 'Networking'],
    years_of_experience: 6,
    is_accepting_assignments: true,
    is_active: true,
    is_email_verified: true,
    created_at: '2026-01-01',
    ...overrides,
  };
}

beforeEach(() => {
  listManageTrainers.mockReset();
  push.mockReset();
});

describe('TrainersHub', () => {
  it('renders a trainer row', async () => {
    listManageTrainers.mockResolvedValue(page([trainerRow()]));
    render(<TrainersHub />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    expect(screen.getByText('Senior trainer')).toBeInTheDocument();
    expect(screen.getByText('6 yrs')).toBeInTheDocument();
  });

  it('renders "No data" for the workload columns the list endpoint does not carry yet', async () => {
    listManageTrainers.mockResolvedValue(page([trainerRow()]));
    render(<TrainersHub />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    expect(screen.getAllByText('No data').length).toBeGreaterThanOrEqual(2);
  });

  it('shows an empty state when no trainers match', async () => {
    listManageTrainers.mockResolvedValue(page([]));
    render(<TrainersHub />);
    await waitFor(() => expect(screen.getByText('No trainers match these filters')).toBeInTheDocument());
  });

  it('shows an error with retry', async () => {
    listManageTrainers.mockRejectedValue(new ApiError(500, 'server_error', 'Could not load trainers.', 'req-1'));
    render(<TrainersHub />);
    await waitFor(() => expect(screen.getByText('Could not load trainers.')).toBeInTheDocument());
  });

  it('sends a search to the server', async () => {
    listManageTrainers.mockResolvedValue(page([trainerRow()]));
    render(<TrainersHub />);
    await waitFor(() => expect(listManageTrainers).toHaveBeenCalledTimes(1));
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Search'), 'tina');
    await waitFor(() =>
      expect(listManageTrainers).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'tina' })),
    );
  });

  it('opens the trainer on row activation', async () => {
    listManageTrainers.mockResolvedValue(page([trainerRow()]));
    render(<TrainersHub />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByText('Tina Trainer'));
    expect(push).toHaveBeenCalledWith('/manage/trainers/trainer-1');
  });
});
