/**
 * The student's hand-in form.
 *
 * The screen's job is to offer the input the assignment actually asks for and
 * to show what the API refused. Both were broken for one submission kind: a
 * `link` assignment got a file picker and a textarea and no URL box, so it
 * could not be handed in, and the `link_url` error that came back had no field
 * to render it and vanished.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MyAssignmentsPage from '@/app/my-assignments/page';
import { ApiError } from '@/lib/api';
import type { StudentAssignment, SubmissionKind } from '@/types/api';

const listMyAssignments = vi.hoisted(() => vi.fn());
const submitAssignment = vi.hoisted(() => vi.fn());
vi.mock('@/lib/assignments', () => ({
  listMyAssignments,
  submitAssignment,
  submissionFileUrl: (id: string) => `/files/${id}`,
}));
vi.mock('@/components/require-auth', () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));

function assignment(kind: SubmissionKind): StudentAssignment {
  return {
    id: `a-${kind}`,
    code: 'GRS-A-00005',
    course: 'c-1',
    course_title: 'DevOps Engineering',
    module: null,
    lesson: null,
    title: 'Docker Compose — a three-tier stack',
    instructions: 'Hand in the compose file as a repository link.',
    submission_kind: kind,
    max_marks: '100.00',
    passing_marks: null,
    due_at: '2026-10-06T12:30:00Z',
    allow_late: false,
    late_cutoff_at: null,
    allow_resubmission: false,
    max_attempts: 1,
    status: 'published',
    is_open: true,
    attachments: [],
    my_submission: null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  submitAssignment.mockResolvedValue({});
});

function load(kind: SubmissionKind) {
  listMyAssignments.mockResolvedValue({
    count: 1,
    page: 1,
    page_size: 25,
    total_pages: 1,
    next: null,
    previous: null,
    results: [assignment(kind)],
  });
  return render(<MyAssignmentsPage />);
}

describe('the hand-in form offers the input the assignment asks for', () => {
  it('gives a link assignment a URL field and no file picker', async () => {
    load('link');
    expect(await screen.findByLabelText('Link')).toHaveAttribute('type', 'url');
    expect(screen.queryByLabelText('Files')).toBeNull();
    expect(screen.queryByLabelText('Written answer')).toBeNull();
  });

  it('sends the typed link as link_url', async () => {
    load('link');
    const field = await screen.findByLabelText('Link');
    fireEvent.change(field, { target: { value: 'https://example.test/compose' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));

    await waitFor(() => expect(submitAssignment).toHaveBeenCalled());
    expect(submitAssignment.mock.calls[0]?.[1]).toMatchObject({
      link_url: 'https://example.test/compose',
    });
  });

  it('gives a file assignment only a file picker', async () => {
    load('file');
    expect(await screen.findByLabelText('Files')).toHaveAttribute('type', 'file');
    expect(screen.queryByLabelText('Written answer')).toBeNull();
    expect(screen.queryByLabelText('Link')).toBeNull();
  });

  it('gives a text assignment only a written answer', async () => {
    load('text');
    expect(await screen.findByLabelText('Written answer')).toBeInTheDocument();
    expect(screen.queryByLabelText('Files')).toBeNull();
    expect(screen.queryByLabelText('Link')).toBeNull();
  });

  it('gives an any assignment all three', async () => {
    load('any');
    expect(await screen.findByLabelText('Files')).toBeInTheDocument();
    expect(screen.getByLabelText('Written answer')).toBeInTheDocument();
    expect(screen.getByLabelText('Link')).toBeInTheDocument();
  });
});

describe('the API’s refusal is shown, not swallowed', () => {
  it('shows a link_url error on the link field', async () => {
    load('link');
    submitAssignment.mockRejectedValue(
      new ApiError(400, 'application_error', 'The submitted data is invalid.', 'req-1', {
        link_url: ['This assignment requires a link.'],
      }),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Submit' }));
    expect(await screen.findByText('This assignment requires a link.')).toBeInTheDocument();
  });

  it('shows an error keyed to a field this kind does not render', async () => {
    // A `files` refusal on a link form has nowhere of its own to go. Before the
    // fix such a message was dropped and Submit looked dead.
    load('link');
    submitAssignment.mockRejectedValue(
      new ApiError(400, 'application_error', 'The submitted data is invalid.', 'req-2', {
        files: ['Submit at most 5 files in one attempt.'],
      }),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Submit' }));
    expect(
      await screen.findByText('Submit at most 5 files in one attempt.'),
    ).toBeInTheDocument();
  });
});
