/**
 * The live paper.
 *
 * Every question carries the bank's `negative_marks` whether or not the exam
 * applies them — `grade_attempt` gates the deduction on the exam's own
 * `negative_marking` flag. The player read the per-question figure alone and so
 * told candidates "−0.25 if wrong" on a paper whose instructions, and whose
 * card on `/exams`, both said there is no negative marking.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ExamPage from '@/app/exams/[examId]/page';
import type { AttemptPaper } from '@/types/api';

const startAttempt = vi.hoisted(() => vi.fn());
vi.mock('@/lib/exams', () => ({
  startAttempt,
  getAttemptPaper: vi.fn(),
  saveAnswer: vi.fn(),
  submitAttempt: vi.fn(),
}));
vi.mock('next/navigation', () => ({ useParams: () => ({ examId: 'e-1' }) }));
vi.mock('@/components/require-auth', () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));

function paper(negativeMarking: boolean): AttemptPaper {
  return {
    attempt: {
      id: 'at-1',
      exam: 'e-1',
      exam_code: 'GRS-F-00001',
      exam_title: 'Mid-course examination',
      attempt_number: 1,
      status: 'in_progress',
      started_at: '2026-09-26T04:00:00Z',
      expires_at: '2026-09-26T05:30:00Z',
      submitted_at: null,
      seconds_remaining: 3600,
      results_published: false,
      negative_marking: negativeMarking,
    },
    questions: [
      {
        id: 'q-1',
        position: 0,
        section: 'Multiple choice',
        question_type: 'mcq',
        text: 'Which object keeps a Pod running?',
        marks: '3.00',
        // The bank's penalty, copied onto the paper whatever the exam does
        // with it.
        negative_marks: '0.25',
        options: [{ id: 'o-1', text: 'A Deployment' }],
        selected_options: [],
        text_answer: '',
        answered_filename: '',
      },
    ],
  };
}

beforeEach(() => vi.clearAllMocks());

describe('the marks line on a question', () => {
  it('promises no penalty on an exam that deducts nothing', async () => {
    startAttempt.mockResolvedValue(paper(false));
    render(<ExamPage />);

    await waitFor(() => expect(screen.getByTestId('exam-question')).toBeInTheDocument());
    expect(screen.getByText('3.00 marks')).toBeInTheDocument();
    expect(screen.queryByText(/if wrong/)).toBeNull();
  });

  it('states the penalty on an exam that does deduct', async () => {
    startAttempt.mockResolvedValue(paper(true));
    render(<ExamPage />);

    await waitFor(() => expect(screen.getByTestId('exam-question')).toBeInTheDocument());
    expect(screen.getByText(/−0.25 if wrong/)).toBeInTheDocument();
  });
});
