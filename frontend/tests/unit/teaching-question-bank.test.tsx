/**
 * `/teaching/questions` — the bank is a searchable, filterable, paged list.
 *
 * It used to call `listQuestions()` with no query at all and render `results`:
 * a trainer with fifty-seven questions saw twenty-five of them, in one fixed
 * order, with no control on the page to reach the rest — and every filter the
 * API has always supported (`question_type`, `difficulty`, `tag`, `is_active`,
 * `search`) was unreachable from the only screen that reads the bank.
 *
 * These tests pin the query the screen sends for each control, and that the
 * page controls come from the server's envelope rather than the row count.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Paginated, Question } from '@/types/api';

const listQuestions = vi.hoisted(() => vi.fn());
vi.mock('@/lib/exams', async () => {
  const actual = await vi.importActual<typeof import('@/lib/exams')>('@/lib/exams');
  return { ...actual, listQuestions };
});

const listBatches = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, listBatches };
});

vi.mock('@/components/require-auth', () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));

import QuestionBankPage from '@/app/teaching/questions/page';

function question(overrides: Partial<Question> = {}): Question {
  return {
    id: 'q1',
    course: 'c1',
    course_title: 'DevOps Engineering',
    module: null,
    module_title: null,
    question_type: 'mcq',
    text: 'Which command lists running containers?',
    difficulty: 'medium',
    marks: '2.00',
    negative_marks: '0.00',
    tags: ['docker'],
    explanation: '',
    answer_key: [],
    options: [],
    is_active: true,
    created_at: '2026-09-01T09:00:00Z',
    updated_at: '2026-09-01T09:00:00Z',
    ...overrides,
  } as Question;
}

function page(
  results: Question[],
  envelope: Partial<Paginated<Question>> = {},
): Paginated<Question> {
  return {
    count: 57,
    page: 1,
    page_size: 20,
    total_pages: 3,
    next: 'http://api.test/next',
    previous: null,
    results,
    ...envelope,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listBatches.mockResolvedValue({
    count: 0,
    page: 1,
    page_size: 100,
    total_pages: 1,
    next: null,
    previous: null,
    results: [],
  });
});

describe('the question bank', () => {
  it("shows the server's count and page controls, not just the first page's rows", async () => {
    listQuestions.mockResolvedValue(page([question()]));
    render(<QuestionBankPage />);

    await waitFor(() =>
      expect(screen.getByText('Which command lists running containers?')).toBeInTheDocument(),
    );
    expect(screen.getByText('Showing 1–20 of 57')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
  });

  it('asks for the next page when the trainer pages forward', async () => {
    const user = userEvent.setup();
    listQuestions.mockResolvedValue(page([question()]));
    render(<QuestionBankPage />);
    await waitFor(() =>
      expect(screen.getByText('Which command lists running containers?')).toBeInTheDocument(),
    );

    listQuestions.mockResolvedValue(
      page([question({ id: 'q2', text: 'What does `docker compose up` do?' })], { page: 2 }),
    );
    await user.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() =>
      expect(listQuestions).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 }),
        expect.anything(),
      ),
    );
    expect(await screen.findByText('What does `docker compose up` do?')).toBeInTheDocument();
  });

  it('sends the type filter and drops back to page 1', async () => {
    const user = userEvent.setup();
    listQuestions.mockResolvedValue(page([question()]));
    render(<QuestionBankPage />);
    await waitFor(() =>
      expect(screen.getByText('Which command lists running containers?')).toBeInTheDocument(),
    );

    await user.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() =>
      expect(listQuestions).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 }),
        expect.anything(),
      ),
    );

    await user.selectOptions(screen.getByLabelText('Type'), 'true_false');

    await waitFor(() =>
      expect(listQuestions).toHaveBeenLastCalledWith(
        expect.objectContaining({ question_type: 'true_false', page: 1 }),
        expect.anything(),
      ),
    );
  });

  it('sends the difficulty and is_active filters', async () => {
    const user = userEvent.setup();
    listQuestions.mockResolvedValue(page([question()]));
    render(<QuestionBankPage />);
    await waitFor(() =>
      expect(screen.getByText('Which command lists running containers?')).toBeInTheDocument(),
    );

    await user.selectOptions(screen.getByLabelText('Difficulty'), 'hard');
    await waitFor(() =>
      expect(listQuestions).toHaveBeenLastCalledWith(
        expect.objectContaining({ difficulty: 'hard' }),
        expect.anything(),
      ),
    );

    await user.selectOptions(screen.getByLabelText('In use'), 'false');
    await waitFor(() =>
      expect(listQuestions).toHaveBeenLastCalledWith(
        expect.objectContaining({ is_active: 'false' }),
        expect.anything(),
      ),
    );
  });

  it('normalises a typed tag to the form the bank stores', async () => {
    const user = userEvent.setup();
    listQuestions.mockResolvedValue(page([question()]));
    render(<QuestionBankPage />);
    await waitFor(() =>
      expect(screen.getByText('Which command lists running containers?')).toBeInTheDocument(),
    );

    // The create form writes tags lowercased and hyphenated, and the server
    // matches a whole tag — so "Shell Scripting" has to become
    // "shell-scripting" or it finds nothing.
    await user.type(screen.getByLabelText('Tag'), 'Shell Scripting');

    await waitFor(() =>
      expect(listQuestions).toHaveBeenLastCalledWith(
        expect.objectContaining({ tag: 'shell-scripting' }),
        expect.anything(),
      ),
    );
  });

  it('debounces the search box into a query parameter', async () => {
    const user = userEvent.setup();
    listQuestions.mockResolvedValue(page([question()]));
    render(<QuestionBankPage />);
    await waitFor(() =>
      expect(screen.getByText('Which command lists running containers?')).toBeInTheDocument(),
    );

    await user.type(screen.getByLabelText('Search'), 'containers');

    await waitFor(() =>
      expect(listQuestions).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: 'containers' }),
        expect.anything(),
      ),
    );
  });

  it('distinguishes "nothing matches" from "the bank is empty"', async () => {
    const user = userEvent.setup();
    listQuestions.mockResolvedValue(
      page([], { count: 0, total_pages: 1, next: null, previous: null }),
    );
    render(<QuestionBankPage />);

    await waitFor(() => expect(screen.getByText('The bank is empty')).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText('Difficulty'), 'hard');
    expect(await screen.findByText('No question matches that')).toBeInTheDocument();
  });
});
