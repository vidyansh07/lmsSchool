/**
 * `/my-projects` — the student's own project list.
 *
 * What this pins is one thing the screen got wrong: it printed `end_date`
 * straight from the API, so the only date on the card read "2026-10-14" while
 * every sibling student screen reads "14 Oct 2026". `lib/format` is the one
 * place in this app that decides what a date looks like, and a screen that
 * bypasses it is a screen that disagrees with the one next to it.
 */
import { render, screen, waitFor } from '@testing-library/react';

import { formatDate } from '@/lib/format';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MyProjectsPage from '@/app/my-projects/page';
import type { StudentProject } from '@/types/api';

const listMyProjects = vi.hoisted(() => vi.fn());
const listRequiredProjectProgress = vi.hoisted(() => vi.fn());
vi.mock('@/lib/projects', async () => {
  const actual = await vi.importActual<typeof import('@/lib/projects')>('@/lib/projects');
  return { ...actual, listMyProjects, listRequiredProjectProgress };
});

vi.mock('@/components/require-auth', () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));

function project(overrides: Partial<StudentProject> = {}): StudentProject {
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
    end_date: '2026-10-14',
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
    assigned_count: 1,
    created_at: '2026-09-01T09:00:00Z',
    updated_at: '2026-09-01T09:00:00Z',
    my_work: null,
    ...overrides,
  } as StudentProject;
}

function page(results: StudentProject[]) {
  return {
    count: results.length,
    page: 1,
    page_size: 20,
    total_pages: 1,
    next: null,
    previous: null,
    results,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listRequiredProjectProgress.mockResolvedValue([]);
});

describe('MyProjects', () => {
  it('formats the due date rather than printing the API string', async () => {
    listMyProjects.mockResolvedValue(page([project()]));
    render(<MyProjectsPage />);

    await waitFor(() => expect(screen.getByTestId('project-card')).toBeInTheDocument());
    // Asserted through `formatDate` itself, not against a spelled-out date:
    // the rendering is `toLocaleDateString`'s, so it is "14 Oct 2026" under
    // en-GB and "Oct 14, 2026" under en-US, and a test that hard-codes either
    // passes or fails on the machine's locale rather than on the code. What
    // this screen promises is that the date goes through `lib/format` — so the
    // formatted form is present and the API's own string is not.
    expect(screen.getByTestId('project-card')).toHaveTextContent(
      `due ${formatDate('2026-10-14')}`,
    );
    expect(screen.queryByText(/2026-10-14/)).not.toBeInTheDocument();
  });

  it('still says "no date set" for a project with no due date at all', async () => {
    listMyProjects.mockResolvedValue(page([project({ end_date: null })]));
    render(<MyProjectsPage />);

    await waitFor(() => expect(screen.getByTestId('project-card')).toBeInTheDocument());
    expect(screen.getByText(/due no date set/)).toBeInTheDocument();
  });
});
