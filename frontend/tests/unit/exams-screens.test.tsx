/**
 * The candidate's examination screens.
 *
 * Three statements on these screens contradicted either the data behind them or
 * each other: a marked-but-unreleased attempt was badged "Graded" beside a body
 * saying the result was not released; the only control that could open a paper
 * disappeared once the first of two allowed attempts was submitted; a live paper
 * promised a penalty for a wrong answer on an exam that deducts nothing; and a
 * written answer given partial credit was badged "Incorrect".
 */
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AttemptReviewPage from '@/app/attempts/[attemptId]/page';
import ExamsPage from '@/app/exams/page';
import { answerOutcome, attemptBadge } from '@/lib/academic-labels';
import type { AttemptResult, Exam } from '@/types/api';

const listMyExams = vi.hoisted(() => vi.fn());
const listMyAttempts = vi.hoisted(() => vi.fn());
const getAttemptReview = vi.hoisted(() => vi.fn());
vi.mock('@/lib/exams', () => ({ listMyExams, listMyAttempts, getAttemptReview }));
vi.mock('next/navigation', () => ({ useParams: () => ({ attemptId: 'at-1' }) }));
vi.mock('@/components/require-auth', () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));

function exam(overrides: Partial<Exam> = {}): Exam {
  return {
    id: 'e-1',
    code: 'GRS-F-00001',
    batch: 'b-1',
    batch_code: 'GRS-B-00025',
    course: 'c-1',
    course_title: 'DevOps Engineering',
    title: 'Mid-course examination',
    description: 'Two attempts allowed; the better one counts.',
    instructions: 'There is no negative marking.',
    opens_at: '2026-09-25T03:30:00Z',
    closes_at: '2026-10-06T12:30:00Z',
    duration_minutes: 90,
    max_attempts: 2,
    passing_marks: null,
    negative_marking: false,
    shuffle_questions: true,
    shuffle_options: true,
    results_published: false,
    results_published_at: null,
    status: 'published',
    published_at: '2026-09-23T03:30:00Z',
    is_open: true,
    total_questions: 14,
    attempt_count: 1,
    sections: [],
    created_at: '2026-09-23T03:30:00Z',
    updated_at: '2026-09-23T03:30:00Z',
    ...overrides,
  };
}

function attempt(overrides: Partial<AttemptResult> = {}): AttemptResult {
  return {
    id: 'at-1',
    exam: 'e-1',
    exam_code: 'GRS-F-00001',
    exam_title: 'Mid-course examination',
    attempt_number: 1,
    status: 'graded',
    submitted_at: '2026-09-25T21:06:00Z',
    graded_at: '2026-09-26T08:13:00Z',
    total_score: '14.00',
    max_score: '27.00',
    is_passing: true,
    percentage: 51.85,
    results_published: false,
    ...overrides,
  };
}

function page(exams: Exam[], attempts: AttemptResult[]) {
  const envelope = <T,>(results: T[]) => ({
    count: results.length,
    page: 1,
    page_size: 25,
    total_pages: 1,
    next: null,
    previous: null,
    results,
  });
  listMyExams.mockResolvedValue(envelope(exams));
  listMyAttempts.mockResolvedValue(envelope(attempts));
}

beforeEach(() => vi.clearAllMocks());

describe('attemptBadge', () => {
  it('does not claim "Graded" while the result is withheld', () => {
    expect(attemptBadge({ status: 'graded', results_published: false })).toEqual({
      label: 'Marked, result not released',
      variant: 'neutral',
    });
  });

  it('says "Graded" once the exam releases results', () => {
    expect(attemptBadge({ status: 'graded', results_published: true })).toEqual({
      label: 'Graded',
      variant: 'success',
    });
  });

  it('leaves every other status alone', () => {
    expect(attemptBadge({ status: 'in_progress', results_published: false }).label).toBe(
      'In progress',
    );
    expect(attemptBadge({ status: 'submitted', results_published: false }).label).toBe(
      'Submitted, awaiting marking',
    );
    expect(attemptBadge({ status: 'expired', results_published: true }).variant).toBe('error');
  });
});

describe('answerOutcome', () => {
  it('calls partial credit partly correct, not incorrect', () => {
    // The real row: a long answer marked 3.00 of 5.00 with the feedback "Clear
    // and complete". `mark_written_answer` sets `is_correct = awarded >= marks`,
    // so the flag alone says `false`.
    expect(answerOutcome({ awarded: '3.00', marks: '5.00', is_correct: false })).toEqual({
      label: 'Partly correct',
      variant: 'warning',
    });
  });

  it('calls a zero-mark answer incorrect', () => {
    expect(answerOutcome({ awarded: '0.00', marks: '2.00', is_correct: false })).toEqual({
      label: 'Incorrect',
      variant: 'error',
    });
  });

  it('calls a full-mark answer correct', () => {
    expect(answerOutcome({ awarded: '2.00', marks: '2.00', is_correct: true }).label).toBe(
      'Correct',
    );
  });

  it('says a negatively marked answer is incorrect, not partly correct', () => {
    expect(answerOutcome({ awarded: '-0.25', marks: '3.00', is_correct: false }).label).toBe(
      'Incorrect',
    );
  });

  it('still says a question is waiting for a person when nothing is marked', () => {
    expect(answerOutcome({ awarded: null, marks: '5.00', is_correct: null }).label).toBe(
      'Marked by a person',
    );
  });
});

describe('the examinations list', () => {
  it('offers the second attempt an exam allows after the first is marked', async () => {
    page([exam()], [attempt()]);
    render(<ExamsPage />);

    const card = await screen.findByTestId('exam-card');
    expect(within(card).getByRole('link', { name: /start attempt 2/i })).toHaveAttribute(
      'href',
      '/exams/e-1',
    );
    expect(within(card).getByTestId('attempts-left')).toHaveTextContent('1 of 2 attempts left.');
  });

  it('offers nothing once every attempt is used', async () => {
    page(
      [exam()],
      [attempt(), attempt({ id: 'at-2', attempt_number: 2, status: 'submitted' })],
    );
    render(<ExamsPage />);

    const card = await screen.findByTestId('exam-card');
    expect(within(card).queryByRole('link', { name: /start|continue/i })).toBeNull();
  });

  it('resumes a running attempt rather than starting another', async () => {
    page([exam()], [attempt({ status: 'in_progress', submitted_at: null })]);
    render(<ExamsPage />);

    const card = await screen.findByTestId('exam-card');
    expect(within(card).getByRole('link', { name: /continue the examination/i })).toBeTruthy();
  });

  it('shows the newest attempt, not the oldest, whatever order the API sends', async () => {
    // `MyAttemptsView` orders newest-first; a map built straight from that list
    // kept the *first* attempt as the survivor of each exam.
    page(
      [exam({ max_attempts: 3 })],
      [
        attempt({ id: 'at-2', attempt_number: 2, status: 'in_progress', submitted_at: null }),
        attempt({ id: 'at-1', attempt_number: 1, status: 'graded' }),
      ],
    );
    render(<ExamsPage />);

    const card = await screen.findByTestId('exam-card');
    expect(within(card).getByText('In progress')).toBeInTheDocument();
    expect(within(card).queryByText(/result not released/i)).toBeNull();
  });

  it('never badges the card differently from the body it sits above', async () => {
    page([exam()], [attempt()]);
    render(<ExamsPage />);

    const card = await screen.findByTestId('exam-card');
    expect(within(card).queryByText('Graded')).toBeNull();
    expect(within(card).getByText('Marked, result not released')).toBeInTheDocument();
    expect(within(card).getByText(/results have not been released yet/i)).toBeInTheDocument();
  });
});

describe('the marked paper', () => {
  it('does not badge partial credit "Incorrect" beside its own marks', async () => {
    getAttemptReview.mockResolvedValue({
      attempt: attempt({ results_published: true }),
      questions: [
        {
          position: 0,
          question_text: 'Explain a rolling deployment.',
          question_type: 'long_answer',
          marks: '5.00',
          awarded: '3.00',
          is_correct: false,
          explanation: '',
          marker_feedback: 'Clear and complete.',
        },
      ],
    });
    render(<AttemptReviewPage />);

    const card = await screen.findByTestId('review-question');
    expect(within(card).getByText('Partly correct')).toBeInTheDocument();
    expect(within(card).queryByText('Incorrect')).toBeNull();
    expect(within(card).getByText(/3.00 of 5.00/)).toBeInTheDocument();
  });
});
