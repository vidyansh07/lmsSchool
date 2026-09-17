/**
 * The Student 360 Activities tab: loading, empty, error and success, for
 * one student's own activity queue. Not covered anywhere else —
 * `student-360-page.test.tsx` mocks this component out entirely (see its
 * own comment on why: the page's tests are about the page, not this tab's
 * own fetch/filter/render logic), so this is this component's first test.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { StudentActivitiesTab } from '@/components/students/student-activities-tab';
import { ApiError } from '@/lib/api';
import type { Activity, Paginated } from '@/types/api';

const listStudentActivities = vi.hoisted(() => vi.fn());
const listActivityTypes = vi.hoisted(() => vi.fn());
vi.mock('@/lib/work', async () => {
  const actual = await vi.importActual<typeof import('@/lib/work')>('@/lib/work');
  return { ...actual, listStudentActivities, listActivityTypes };
});
// The drawer has its own dedicated tests (`activity-drawer.test.tsx`); here
// it would only add unrelated fetches to mock.
vi.mock('@/components/work/activity-drawer', () => ({ ActivityDrawer: () => null }));

function row(overrides: Partial<Activity> = {}): Activity {
  return {
    id: 'a1',
    title: 'Mock interview with Priya',
    status: 'completed',
    priority: 'normal',
    planned_at: '2026-09-14T10:00:00Z',
    due_at: '2026-09-14T10:00:00Z',
    completed_at: '2026-09-14T10:30:00Z',
    created_at: '2026-09-10T09:00:00Z',
    student: { id: 's1', name: 'Priya Patel', student_id: 'STU-001' },
    type: { id: 't1', slug: 'mock-interview', name: 'Mock Interview', category: 'interview' },
    batch: null,
    assigned_to: { id: 'u1', name: 'Tina Trainer' },
    created_by: { id: 'u2', name: 'Tina Trainer' },
    counts: { history: 1 },
    ...overrides,
  };
}

function paginated(results: Activity[]): Paginated<Activity> {
  return { count: results.length, page: 1, page_size: 25, total_pages: 1, next: null, previous: null, results };
}

describe('StudentActivitiesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listActivityTypes.mockResolvedValue({ results: [] });
  });

  it('shows a loading state, then renders rows on success', async () => {
    listStudentActivities.mockResolvedValue(paginated([row()]));
    render(<StudentActivitiesTab studentId="student-1" />);

    expect(screen.getByText('Loading activities…')).toBeInTheDocument();
    expect(await screen.findByText('Mock interview with Priya')).toBeInTheDocument();
    expect(within(screen.getByRole('table')).getByText('Tina Trainer')).toBeInTheDocument();
    expect(listStudentActivities).toHaveBeenCalledWith('student-1', expect.any(Object));
  });

  it('shows an empty state when this student has no activities matching the filters', async () => {
    listStudentActivities.mockResolvedValue(paginated([]));
    render(<StudentActivitiesTab studentId="student-1" />);

    expect(await screen.findByText('No activities match these filters')).toBeInTheDocument();
    expect(
      screen.getByText(/Widen the filters, or check back once work is assigned/i),
    ).toBeInTheDocument();
  });

  it('shows an error state with a retry that re-fetches', async () => {
    listStudentActivities.mockRejectedValueOnce(
      new ApiError(500, 'server_error', 'Down', 'req-student-activities-1'),
    );
    render(<StudentActivitiesTab studentId="student-1" />);

    expect(await screen.findByText('Could not load activities')).toBeInTheDocument();
    expect(screen.getByText(/req-student-activities-1/)).toBeInTheDocument();

    listStudentActivities.mockResolvedValueOnce(paginated([row()]));
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(listStudentActivities).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Mock interview with Priya')).toBeInTheDocument();
  });
});
