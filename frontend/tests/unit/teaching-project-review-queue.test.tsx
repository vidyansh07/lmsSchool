/**
 * `/teaching/projects/[projectId]` — the review queue's list contract.
 *
 * The screen used to render `listProjectWork(projectId).results` and print
 * `results.length` in the card title, so a cohort of sixty-nine read
 * "Submitted work (25)" — the page size, offered as the total — with no
 * control to reach the other forty-four. The trainer's own dashboard links
 * here to review one specific piece of work, and on a cohort that size that
 * row was off-page and unreachable.
 *
 * So these tests pin three things: the count comes from the server's envelope,
 * the pagination control asks for the next page, and the status filter is sent
 * as a query parameter with the page reset.
 */
import { render, screen, waitFor } from '@testing-library/react';

import { formatDate } from '@/lib/format';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Paginated, Project, ReviewerProjectWork } from '@/types/api';

const getProject = vi.hoisted(() => vi.fn());
const listProjectWork = vi.hoisted(() => vi.fn());
vi.mock('@/lib/projects', async () => {
  const actual = await vi.importActual<typeof import('@/lib/projects')>('@/lib/projects');
  return { ...actual, getProject, listProjectWork };
});

vi.mock('@/components/require-auth', () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('next/navigation', () => ({
  useParams: () => ({ projectId: 'p1' }),
}));

import TeachingProjectPage from '@/app/teaching/projects/[projectId]/page';

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    code: 'GRS-P-00003',
    course: 'c1',
    course_title: 'DevOps Engineering',
    module: null,
    module_title: null,
    batch: null,
    batch_code: null,
    title: 'Major project — a production-style pipeline',
    description: '',
    instructions: '',
    deliverables: '',
    kind: 'major',
    is_required: true,
    start_date: null,
    end_date: null,
    requires_repository_url: false,
    requires_deployment_url: false,
    max_marks: '100.00',
    passing_marks: '40.00',
    rubric: [],
    reviewer: null,
    reviewer_name: null,
    status: 'published',
    published_at: '2026-09-01T09:00:00Z',
    is_open: true,
    assigned_count: 69,
    created_at: '2026-09-01T09:00:00Z',
    updated_at: '2026-09-01T09:00:00Z',
    ...overrides,
  };
}

function work(overrides: Partial<ReviewerProjectWork> = {}): ReviewerProjectWork {
  return {
    id: 'w1',
    project: 'p1',
    project_code: 'GRS-P-00003',
    project_title: 'Major project — a production-style pipeline',
    status: 'submitted',
    repository_url: '',
    deployment_url: '',
    notes: '',
    submitted_at: '2026-09-20T10:00:00Z',
    submission_count: 1,
    is_late: false,
    marks_awarded: null,
    max_marks: '100.00',
    rubric_scores: {},
    is_passing: null,
    is_open_to_student: false,
    feedback: '',
    reviewed_at: null,
    files: [],
    enrollment: 'e1',
    student_id: 'GRS-S-01067',
    student_name: 'Yash Yadav',
    batch_code: 'GRS-B-00025',
    reviewer_name: null,
    ...overrides,
    // `Partial` makes every inherited field optional, so the spread widens
    // `created_at` to `string | undefined`; the base above always supplies one.
  } as ReviewerProjectWork;
}

/** One page of a much longer queue — the shape the bug hid behind. */
function page(
  results: ReviewerProjectWork[],
  envelope: Partial<Paginated<ReviewerProjectWork>> = {},
): Paginated<ReviewerProjectWork> {
  return {
    count: 69,
    page: 1,
    page_size: 25,
    total_pages: 3,
    next: 'http://api.test/next',
    previous: null,
    results,
    ...envelope,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getProject.mockResolvedValue(project());
});

describe('the project review queue', () => {
  it("reports the server's count, not the number of rows on this page", async () => {
    listProjectWork.mockResolvedValue(page([work()]));
    render(<TeachingProjectPage />);

    await waitFor(() => expect(screen.getByText('The review queue (69)')).toBeInTheDocument());
    // And says where in the queue the reviewer is, rather than implying there
    // is nothing else.
    expect(screen.getByText('Showing 1–25 of 69')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
  });

  it('asks for the next page when the reviewer pages forward', async () => {
    const user = userEvent.setup();
    listProjectWork.mockResolvedValue(page([work()]));
    render(<TeachingProjectPage />);
    await waitFor(() => expect(screen.getByText('Yash Yadav')).toBeInTheDocument());

    listProjectWork.mockResolvedValue(
      page([work({ id: 'w2', student_name: 'Aisha Choudhary' })], { page: 2, previous: 'p' }),
    );
    await user.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() =>
      expect(listProjectWork).toHaveBeenLastCalledWith('p1', expect.objectContaining({ page: 2 })),
    );
    expect(await screen.findByText('Aisha Choudhary')).toBeInTheDocument();
  });

  it('sends the status filter to the server and returns to page 1', async () => {
    const user = userEvent.setup();
    listProjectWork.mockResolvedValue(page([work()]));
    render(<TeachingProjectPage />);
    await waitFor(() => expect(screen.getByText('Yash Yadav')).toBeInTheDocument());

    // Page forward first, so the reset to page 1 is observable rather than the
    // default.
    listProjectWork.mockResolvedValue(page([work()], { page: 2, previous: 'p' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() =>
      expect(listProjectWork).toHaveBeenLastCalledWith('p1', expect.objectContaining({ page: 2 })),
    );

    listProjectWork.mockResolvedValue(
      page([work()], { count: 1, total_pages: 1, next: null, previous: null }),
    );
    await user.selectOptions(screen.getByLabelText('Show'), 'submitted');

    await waitFor(() =>
      expect(listProjectWork).toHaveBeenLastCalledWith('p1', { status: 'submitted', page: 1 }),
    );
    expect(await screen.findByText('The review queue (1)')).toBeInTheDocument();
  });

  /**
   * The brief's own subtitle printed `end_date` straight from the API, so the
   * one date on this screen read "2026-10-14" where every sibling screen reads
   * "14 Oct 2026". `lib/format`'s `formatDate` is the one place that decides.
   */
  it('formats the due date rather than printing the API string', async () => {
    getProject.mockResolvedValue(project({ end_date: '2026-10-14' }));
    listProjectWork.mockResolvedValue(page([work()]));
    render(<TeachingProjectPage />);

    await waitFor(() => expect(screen.getByText('The brief')).toBeInTheDocument());
    // Through `formatDate`, not a spelled-out date — see the note in
    // `my-projects-page.test.tsx`: the exact rendering is the locale's.
    expect(screen.getByText(`Due ${formatDate('2026-10-14')}`)).toBeInTheDocument();
    expect(screen.queryByText(/2026-10-14/)).not.toBeInTheDocument();
  });

  it('still says "no date set" for a project with no due date at all', async () => {
    getProject.mockResolvedValue(project({ end_date: null }));
    listProjectWork.mockResolvedValue(page([work()]));
    render(<TeachingProjectPage />);

    await waitFor(() => expect(screen.getByText('The brief')).toBeInTheDocument());
    expect(screen.getByText('Due no date set')).toBeInTheDocument();
  });

  it('says which empty it means when a filter matches nothing', async () => {
    const user = userEvent.setup();
    listProjectWork.mockResolvedValue(page([work()]));
    render(<TeachingProjectPage />);
    await waitFor(() => expect(screen.getByText('Yash Yadav')).toBeInTheDocument());

    listProjectWork.mockResolvedValue(
      page([], { count: 0, total_pages: 1, next: null, previous: null }),
    );
    await user.selectOptions(screen.getByLabelText('Show'), 'approved');

    expect(await screen.findByText('Nothing in that state')).toBeInTheDocument();
  });
});
