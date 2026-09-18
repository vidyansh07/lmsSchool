/**
 * `/admin/trainers` — migrated onto `DataTable` (Phase R6). Covers what the
 * migration must not have changed: every column renders real data, sort
 * still calls `listTrainers` with the same query shape, the availability
 * toggle still drives the same real mutation it did before, and the density
 * toggle persists.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminTrainersPage from '@/app/admin/trainers/page';
import { ApiError } from '@/lib/api';
import type { TrainerListRow } from '@/types/api';

const listTrainers = vi.hoisted(() => vi.fn());
const updateTrainer = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, listTrainers, updateTrainer };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

vi.mock('@/components/export-menu', () => ({ ExportMenu: () => null }));
vi.mock('@/app/admin/trainers/create-trainer-dialog', () => ({ CreateTrainerDialog: () => null }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

function page(results: TrainerListRow[]) {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function trainerRow(overrides: Partial<TrainerListRow> = {}): TrainerListRow {
  return {
    id: 't-1',
    trainer_id: 'GRS-T-001',
    user_id: 'u-1',
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
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    user: { id: 'u-admin', role: 'admin', capabilities: ['trainer.view_any', 'trainer.update_any'] },
    isLoading: false,
    can: (capability: string) => capability === 'trainer.view_any' || capability === 'trainer.update_any',
  });
});

describe('AdminTrainersPage', () => {
  it('renders every column with real data', async () => {
    listTrainers.mockResolvedValue(page([trainerRow()]));
    render(<AdminTrainersPage />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    expect(screen.getByText('GRS-T-001')).toBeInTheDocument();
    expect(screen.getByText('Senior trainer')).toBeInTheDocument();
    expect(screen.getByText('Linux')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
  });

  it('sends the same sort field on the same server request', async () => {
    listTrainers.mockResolvedValue(page([trainerRow()]));
    render(<AdminTrainersPage />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /experience/i }));
    await waitFor(() =>
      expect(listTrainers).toHaveBeenLastCalledWith(
        expect.objectContaining({ ordering: 'years_of_experience' }),
        expect.anything(),
      ),
    );
  });

  it('toggles availability through the same real mutation as before', async () => {
    listTrainers.mockResolvedValue(page([trainerRow({ is_accepting_assignments: true })]));
    updateTrainer.mockResolvedValue(trainerRow({ is_accepting_assignments: false }));
    render(<AdminTrainersPage />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Accepting' }));
    await waitFor(() =>
      expect(updateTrainer).toHaveBeenCalledWith('t-1', { is_accepting_assignments: false }),
    );
  });

  it('shows a badge, not a button, when the caller cannot manage availability', async () => {
    useAuth.mockReturnValue({
      user: { id: 'u-admin', role: 'admin', capabilities: ['trainer.view_any'] },
      isLoading: false,
      can: (capability: string) => capability === 'trainer.view_any',
    });
    listTrainers.mockResolvedValue(page([trainerRow()]));
    render(<AdminTrainersPage />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Accepting' })).not.toBeInTheDocument();
  });

  it('shows an error with retry on failure', async () => {
    listTrainers.mockRejectedValue(new ApiError(500, 'server_error', 'Could not load.', 'req-1'));
    render(<AdminTrainersPage />);
    await waitFor(() => expect(screen.getByText('Could not load trainers')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('persists the density toggle across a re-render', async () => {
    listTrainers.mockResolvedValue(page([trainerRow()]));
    const { unmount } = render(<AdminTrainersPage />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /compact view/i }));
    expect(window.localStorage.getItem('grras.admin-trainers-density')).toBe('compact');
    unmount();

    render(<AdminTrainersPage />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /comfortable view/i })).toBeInTheDocument();
  });
});
