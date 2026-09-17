/**
 * `/teaching/work` — a trainer's own activity queue: every data state, that
 * a filter change re-queries `listMyActivities` with the right parameters,
 * that `?overdue=1` pre-selects the overdue filter (the dashboard tile's
 * link), and that a row opens the shared activity drawer.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { Activity, Paginated } from '@/types/api';

const listMyActivities = vi.hoisted(() => vi.fn());
vi.mock('@/lib/work', async () => {
  const actual = await vi.importActual<typeof import('@/lib/work')>('@/lib/work');
  return { ...actual, listMyActivities };
});

// The drawer has its own dedicated tests (`activity-drawer.test.tsx`); here a
// stand-in that surfaces the id it opened with is enough to prove the row
// click wires through.
vi.mock('@/components/work/activity-drawer', () => ({
  ActivityDrawer: ({ activityId }: { activityId: string | null }) =>
    activityId ? <div data-testid="activity-drawer">{activityId}</div> : null,
}));

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

const mockRouter = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
const mockSearchParams = vi.hoisted(() => ({ value: new URLSearchParams() }));
vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockSearchParams.value,
}));

import TeachingWorkPage from '@/app/teaching/work/page';

function row(overrides: Partial<Activity> = {}): Activity {
  return {
    id: 'a1',
    title: 'Mock interview with Asha',
    status: 'assigned',
    priority: 'normal',
    planned_at: null,
    due_at: '2026-09-20T10:00:00Z',
    completed_at: null,
    created_at: '2026-09-16T09:00:00Z',
    student: { id: 's1', name: 'Asha Rao', student_id: 'STU-001' },
    type: { id: 't1', slug: 'mock-interview', name: 'Mock Interview', category: 'interview' },
    batch: null,
    assigned_to: { id: 'trainer-1', name: 'Trainer One' },
    created_by: { id: 'u2', name: 'Manager One' },
    counts: { history: 0 },
    ...overrides,
  };
}

function paginated(results: Activity[]): Paginated<Activity> {
  return {
    count: results.length,
    page: 1,
    page_size: 25,
    total_pages: 1,
    next: null,
    previous: null,
    results,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockSearchParams.value = new URLSearchParams();
  mockRouter.replace.mockReset();
  useAuth.mockReturnValue({
    user: { id: 'trainer-1', role: 'trainer', capabilities: [] },
    isLoading: false,
    can: () => false,
  });
});

describe('TeachingWorkPage', () => {
  it('shows a loading state while the list is in flight', () => {
    listMyActivities.mockReturnValue(new Promise(() => {}));
    render(<TeachingWorkPage />);
    expect(screen.getByText(/Loading your work/)).toBeInTheDocument();
  });

  it('shows an empty state when nothing matches the filters', async () => {
    listMyActivities.mockResolvedValue(paginated([]));
    render(<TeachingWorkPage />);
    await waitFor(() => expect(screen.getByText('Nothing here')).toBeInTheDocument());
  });

  it('shows an error with retry when the list fails to load', async () => {
    listMyActivities.mockRejectedValue(new ApiError(500, 'error', 'Server exploded.', 'req-1'));
    render(<TeachingWorkPage />);
    await waitFor(() => expect(screen.getByText('Could not load your work')).toBeInTheDocument());
  });

  it("renders the trainer's own activities and opens the drawer on click", async () => {
    const user = userEvent.setup();
    listMyActivities.mockResolvedValue(paginated([row()]));
    render(<TeachingWorkPage />);

    await waitFor(() => expect(screen.getByText('Mock interview with Asha')).toBeInTheDocument());
    expect(listMyActivities).toHaveBeenCalledWith(
      expect.objectContaining({ ordering: 'due_at', page: 1 }),
    );

    await user.click(screen.getByText('Mock interview with Asha'));
    expect(screen.getByTestId('activity-drawer')).toHaveTextContent('a1');
  });

  it('re-queries with the status filter when it changes', async () => {
    const user = userEvent.setup();
    listMyActivities.mockResolvedValue(paginated([row()]));
    render(<TeachingWorkPage />);
    await waitFor(() => expect(screen.getByText('Mock interview with Asha')).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText('Status'), 'completed');

    await waitFor(() =>
      expect(listMyActivities).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'completed' }),
      ),
    );
  });

  it('toggles the overdue filter and re-queries', async () => {
    const user = userEvent.setup();
    listMyActivities.mockResolvedValue(paginated([row()]));
    render(<TeachingWorkPage />);
    await waitFor(() => expect(screen.getByText('Mock interview with Asha')).toBeInTheDocument());

    await user.click(screen.getByLabelText('Overdue'));

    await waitFor(() =>
      expect(listMyActivities).toHaveBeenLastCalledWith(expect.objectContaining({ overdue: 1 })),
    );
  });

  it('pre-selects the overdue filter from `?overdue=1` (the dashboard tile link)', async () => {
    mockSearchParams.value = new URLSearchParams('overdue=1');
    listMyActivities.mockResolvedValue(paginated([]));
    render(<TeachingWorkPage />);

    await waitFor(() =>
      expect(listMyActivities).toHaveBeenCalledWith(expect.objectContaining({ overdue: 1 })),
    );
    expect(screen.getByLabelText('Overdue')).toBeChecked();
  });
});
