import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TrainerWorkTab } from '@/components/manage/trainer-work-tab';
import { ApiError } from '@/lib/api';
import type { Activity, Paginated, TrainerProfile } from '@/types/api';

const getTrainer = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, getTrainer };
});

const listActivities = vi.hoisted(() => vi.fn());
vi.mock('@/lib/work', async () => {
  const actual = await vi.importActual<typeof import('@/lib/work')>('@/lib/work');
  return { ...actual, listActivities };
});

const openedActivityId = vi.hoisted(() => ({ value: null as string | null }));
vi.mock('@/components/work/activity-drawer', () => ({
  ActivityDrawer: ({ activityId }: { activityId: string | null }) => {
    openedActivityId.value = activityId;
    return activityId ? <div data-testid="activity-drawer">Drawer for {activityId}</div> : null;
  },
}));

function trainer(overrides: Partial<TrainerProfile> = {}): TrainerProfile {
  return {
    id: 'trainer-1',
    trainer_id: 'GRS-T-001',
    user: {
      id: 'user-1',
      email: 'tina@example.com',
      first_name: 'Tina',
      last_name: 'Trainer',
      role: 'trainer',
      is_active: true,
      is_email_verified: true,
      date_joined: '2026-01-01T00:00:00Z',
    } as unknown as TrainerProfile['user'],
    professional_title: 'Trainer',
    bio: '',
    skills: [],
    expertise: '',
    qualifications: '',
    years_of_experience: null,
    professional_links: {},
    is_accepting_assignments: true,
    completion_percent: 100,
    is_profile_complete: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function activity(overrides: Partial<Activity> = {}): Activity {
  return {
    id: 'a1',
    title: 'Mock interview with Asha',
    status: 'under_review',
    priority: 'normal',
    planned_at: null,
    due_at: '2026-09-20T10:00:00Z',
    completed_at: null,
    created_at: '2026-09-16T09:00:00Z',
    student: { id: 's1', name: 'Asha Rao', student_id: 'STU-001' },
    type: { id: 't1', slug: 'mock-interview', name: 'Mock Interview', category: 'interview' },
    batch: null,
    assigned_to: { id: 'user-1', name: 'Tina Trainer' },
    created_by: { id: 'u2', name: 'Manager One' },
    counts: { history: 0 },
    ...overrides,
  };
}

function paginated(results: Activity[]): Paginated<Activity> {
  return { count: results.length, page: 1, page_size: 25, total_pages: 1, next: null, previous: null, results };
}

beforeEach(() => {
  getTrainer.mockReset();
  listActivities.mockReset();
  openedActivityId.value = null;
});

describe('TrainerWorkTab', () => {
  it('resolves the trainer to their own user id, then lists that user’s activities', async () => {
    getTrainer.mockResolvedValue(trainer());
    listActivities.mockResolvedValue(paginated([activity()]));
    render(<TrainerWorkTab trainerId="trainer-1" />);

    expect(await screen.findByText('Mock interview with Asha')).toBeInTheDocument();
    expect(getTrainer).toHaveBeenCalledWith('trainer-1');
    expect(listActivities).toHaveBeenCalledWith(expect.objectContaining({ assigned_to: 'user-1' }));
  });

  it('shows an empty state when this trainer has no matching activities', async () => {
    getTrainer.mockResolvedValue(trainer());
    listActivities.mockResolvedValue(paginated([]));
    render(<TrainerWorkTab trainerId="trainer-1" />);
    expect(await screen.findByText('No activities match these filters')).toBeInTheDocument();
  });

  it('shows a retryable error when the activity list fails to load', async () => {
    getTrainer.mockResolvedValue(trainer());
    listActivities.mockRejectedValue(new ApiError(500, 'server_error', 'Down.', 'req-1'));
    render(<TrainerWorkTab trainerId="trainer-1" />);
    expect(await screen.findByText("Could not load this trainer's activities")).toBeInTheDocument();
  });

  it('opens the real activity drawer for a row, review panel included', async () => {
    getTrainer.mockResolvedValue(trainer());
    listActivities.mockResolvedValue(paginated([activity()]));
    const user = userEvent.setup();
    render(<TrainerWorkTab trainerId="trainer-1" />);
    await screen.findByText('Mock interview with Asha');

    await user.click(screen.getByText('Mock interview with Asha'));
    expect(await screen.findByTestId('activity-drawer')).toBeInTheDocument();
    expect(openedActivityId.value).toBe('a1');
  });

  it('re-queries when the status filter changes', async () => {
    getTrainer.mockResolvedValue(trainer());
    listActivities.mockResolvedValue(paginated([]));
    const user = userEvent.setup();
    render(<TrainerWorkTab trainerId="trainer-1" />);
    await waitFor(() => expect(listActivities).toHaveBeenCalledTimes(1));

    await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'under_review');
    await waitFor(() =>
      expect(listActivities).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'under_review' })),
    );
  });
});
