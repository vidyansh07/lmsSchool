import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DsrQueue } from '@/app/dsr/page';
import { ApiError } from '@/lib/api';
import type { DSRListItem } from '@/lib/dsr';
import type { BatchListRow, Paginated, TrainerListRow } from '@/types/api';

const listDsr = vi.hoisted(() => vi.fn());
vi.mock('@/lib/dsr', async () => {
  const actual = await vi.importActual<typeof import('@/lib/dsr')>('@/lib/dsr');
  return { ...actual, listDsr };
});

const reviewDsr = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, reviewDsr };
});

const listBatches = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, listBatches };
});

const listTrainers = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, listTrainers };
});

const mockAuth = vi.hoisted(() => ({ value: { can: () => true } as { can: (capability: string) => boolean } }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => mockAuth.value }));

function page<T>(results: T[], overrides: Partial<Paginated<T>> = {}): Paginated<T> {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results, ...overrides };
}

function dsrRow(overrides: Partial<DSRListItem> = {}): DSRListItem {
  return {
    id: 'dsr-1',
    session: 'session-1',
    session_date: '2026-09-01',
    batch: 'batch-1',
    batch_code: 'GRS-B-001',
    trainer: 'trainer-1',
    trainer_code: 'GRS-T-001',
    trainer_name: 'Tina Trainer',
    report_date: '2026-09-01',
    start_time: '09:00:00',
    end_time: '11:00:00',
    module: null,
    module_title: null,
    planned_topic: 'Linux permissions',
    actual_topic: 'Linux permissions',
    student_count: 14,
    present_count: 12,
    absent_count: 2,
    online_count: 4,
    offline_count: 10,
    teaching_notes: '',
    issues: '',
    student_concerns: '',
    assignment_given: false,
    assessment_conducted: false,
    status: 'submitted',
    is_editable: false,
    submitted_at: '2026-09-01T18:00:00Z',
    reviewed_at: null,
    reviewed_by: null,
    reviewed_by_name: null,
    manager_comments: '',
    created_at: '2026-09-01T08:00:00Z',
    updated_at: '2026-09-01T18:00:00Z',
    ...overrides,
  };
}

function batchRow(overrides: Partial<BatchListRow> = {}): BatchListRow {
  return {
    id: 'batch-1',
    code: 'GRS-B-001',
    name: 'Morning Linux batch',
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    trainer_name: 'Tina Trainer',
    start_date: '2026-04-01',
    end_date: '2026-06-01',
    capacity: 20,
    enrolled_count: 12,
    seats_available: 8,
    status: 'active',
    created_at: '2026-01-01',
    ...overrides,
  };
}

function trainerRow(overrides: Partial<TrainerListRow> = {}): TrainerListRow {
  return {
    id: 'trainer-1',
    trainer_id: 'GRS-T-001',
    user_id: 'u-trainer-1',
    email: 'tina@example.com',
    full_name: 'Tina Trainer',
    professional_title: 'Senior trainer',
    skills: [],
    years_of_experience: 6,
    is_accepting_assignments: true,
    is_active: true,
    is_email_verified: true,
    created_at: '2026-01-01',
    ...overrides,
  };
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

beforeEach(() => {
  listDsr.mockReset();
  reviewDsr.mockReset();
  listBatches.mockReset().mockResolvedValue(page<BatchListRow>([]));
  listTrainers.mockReset().mockResolvedValue(page<TrainerListRow>([]));
  mockAuth.value = { can: () => true };
});

describe('DsrQueue loading, error and empty states', () => {
  it('shows a loading state before the queue arrives', () => {
    listDsr.mockReturnValue(new Promise(() => {}));
    render(<DsrQueue />);
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
  });

  it('shows an error with retry when the queue fails to load, and recovers on retry', async () => {
    listDsr.mockRejectedValueOnce(new ApiError(500, 'server_error', 'Could not load reports.', 'req-1'));
    listDsr.mockResolvedValueOnce(page([dsrRow()]));
    const user = userEvent.setup();
    render(<DsrQueue />);

    await waitFor(() => expect(screen.getByText('Could not load reports.')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(screen.getByText(/Tina Trainer/)).toBeInTheDocument());
  });

  it('reads an empty default queue as good news', async () => {
    listDsr.mockResolvedValue(page([]));
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Nothing awaiting review')).toBeInTheDocument());
    expect(screen.getByText('Every submitted daily status report has been reviewed.')).toBeInTheDocument();
  });

  it('reads an empty filtered view as plain "no results", not as good news', async () => {
    listDsr.mockResolvedValue(page([]));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(listDsr).toHaveBeenCalledTimes(1));

    await user.selectOptions(screen.getByLabelText('Status'), 'approved');
    await waitFor(() => expect(screen.getByText('No reports match these filters')).toBeInTheDocument());
    expect(screen.queryByText('Nothing awaiting review')).not.toBeInTheDocument();
  });
});

describe('DsrQueue row rendering and null handling', () => {
  it('renders a report row with batch, trainer, topic, attendance and status', async () => {
    listDsr.mockResolvedValue(page([dsrRow()]));
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('GRS-B-001')).toBeInTheDocument());
    expect(screen.getByText('Tina Trainer')).toBeInTheDocument();
    expect(screen.getByText('Linux permissions')).toBeInTheDocument();
    expect(screen.getByText('12 / 2')).toBeInTheDocument();
    expect(within(screen.getByRole('table')).getByText('Submitted')).toBeInTheDocument();
  });

  it('links the batch code to the batch’s manage page', async () => {
    listDsr.mockResolvedValue(page([dsrRow()]));
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('GRS-B-001')).toBeInTheDocument());
    expect(screen.getByText('GRS-B-001').closest('a')).toHaveAttribute('href', '/manage/batches/batch-1');
  });

  it('renders "Unknown" for a report with no trainer name on file', async () => {
    listDsr.mockResolvedValue(page([dsrRow({ trainer_name: '' })]));
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Unknown')).toBeInTheDocument());
  });

  it('renders "No data" for a report with no topic recorded', async () => {
    listDsr.mockResolvedValue(page([dsrRow({ actual_topic: '' })]));
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('GRS-B-001')).toBeInTheDocument());
    expect(screen.getByText('No data')).toBeInTheDocument();
  });

  it('renders "No data" for a report with no batch code on file', async () => {
    listDsr.mockResolvedValue(page([dsrRow({ batch_code: '' })]));
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    expect(screen.getByText('No data')).toBeInTheDocument();
  });
});

describe('DsrQueue filters', () => {
  it('opens on the newest-first, awaiting-review default', async () => {
    listDsr.mockResolvedValue(page([]));
    render(<DsrQueue />);
    await waitFor(() =>
      expect(listDsr).toHaveBeenCalledWith(expect.objectContaining({ status: 'submitted', ordering: '-report_date' })),
    );
  });

  it('sends a status filter to the server', async () => {
    listDsr.mockResolvedValue(page([]));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(listDsr).toHaveBeenCalledTimes(1));

    await user.selectOptions(screen.getByLabelText('Status'), 'rejected');
    await waitFor(() => expect(listDsr).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'rejected' })));
  });

  it('sends a batch filter to the server', async () => {
    listDsr.mockResolvedValue(page([]));
    listBatches.mockResolvedValue(page([batchRow()]));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByRole('option', { name: /GRS-B-001/ })).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText('Batch'), 'batch-1');
    await waitFor(() => expect(listDsr).toHaveBeenLastCalledWith(expect.objectContaining({ batch: 'batch-1' })));
  });

  it('sends a trainer filter to the server', async () => {
    listDsr.mockResolvedValue(page([]));
    listTrainers.mockResolvedValue(page([trainerRow()]));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByRole('option', { name: /Tina Trainer/ })).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText('Trainer'), 'trainer-1');
    await waitFor(() => expect(listDsr).toHaveBeenLastCalledWith(expect.objectContaining({ trainer: 'trainer-1' })));
  });

  it('sends a report-date range to the server', async () => {
    listDsr.mockResolvedValue(page([]));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(listDsr).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole('button', { name: 'Today' }));
    await waitFor(() =>
      expect(listDsr).toHaveBeenLastCalledWith(expect.objectContaining({ date_after: today(), date_before: today() })),
    );
  });

  it('does not block the queue when the batch and trainer option lists fail to load', async () => {
    listDsr.mockResolvedValue(page([dsrRow()]));
    listBatches.mockRejectedValue(new ApiError(500, 'server_error', 'Down.', 'req-9'));
    listTrainers.mockRejectedValue(new ApiError(500, 'server_error', 'Down.', 'req-9'));
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    expect(screen.getByLabelText('Batch')).toBeInTheDocument();
  });
});

describe('DsrQueue inline approval', () => {
  it('approves inline with no comment, and the row clears once the server confirms it', async () => {
    listDsr.mockResolvedValueOnce(page([dsrRow()]));
    listDsr.mockResolvedValueOnce(page([]));
    reviewDsr.mockResolvedValue(dsrRow({ status: 'approved' }));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /^approve$/i }));
    expect(reviewDsr).toHaveBeenCalledWith('dsr-1', 'approved', '');
    await waitFor(() => expect(screen.getByText('Nothing awaiting review')).toBeInTheDocument());
  });

  it('rolls back visibly when the approval fails, without reloading the list', async () => {
    listDsr.mockResolvedValue(page([dsrRow()]));
    reviewDsr.mockRejectedValue(new ApiError(409, 'conflict', 'This report was already reviewed.', 'req-2'));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /^approve$/i }));
    await waitFor(() => expect(screen.getByText('This report was already reviewed.')).toBeInTheDocument());
    expect(screen.getByText('Tina Trainer')).toBeInTheDocument();
    expect(listDsr).toHaveBeenCalledTimes(1);
  });

  it('hides every review control from someone without dsr.review', async () => {
    mockAuth.value = { can: () => false };
    listDsr.mockResolvedValue(page([dsrRow()]));
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument();
  });

  it('offers no review controls for a report that already has a final decision', async () => {
    listDsr.mockResolvedValue(page([dsrRow({ status: 'approved' })]));
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /request revision/i })).not.toBeInTheDocument();
  });
});

describe('DsrQueue reject and revision', () => {
  it('does not reject on one click — it opens a comment field first', async () => {
    listDsr.mockResolvedValue(page([dsrRow()]));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /^reject$/i }));
    expect(reviewDsr).not.toHaveBeenCalled();
    expect(screen.getByText('Why is this being rejected?')).toBeInTheDocument();
  });

  it('keeps the reject confirmation disabled until a reason is typed', async () => {
    listDsr.mockResolvedValue(page([dsrRow()]));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^reject$/i }));

    expect(screen.getByRole('button', { name: /^reject$/i })).toBeDisabled();
    await user.type(screen.getByLabelText('Why is this being rejected?'), 'Missed the session entirely.');
    expect(screen.getByRole('button', { name: /^reject$/i })).toBeEnabled();
  });

  it('rejects with the typed comment once confirmed', async () => {
    listDsr.mockResolvedValueOnce(page([dsrRow()]));
    listDsr.mockResolvedValueOnce(page([]));
    reviewDsr.mockResolvedValue(dsrRow({ status: 'rejected' }));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /^reject$/i }));
    await user.type(screen.getByLabelText('Why is this being rejected?'), 'Missed the session entirely.');
    await user.click(screen.getByRole('button', { name: /^reject$/i }));

    expect(reviewDsr).toHaveBeenCalledWith('dsr-1', 'rejected', 'Missed the session entirely.');
  });

  it('asks what needs to change for a revision request, distinctly from a rejection', async () => {
    listDsr.mockResolvedValue(page([dsrRow()]));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /request revision/i }));
    expect(screen.getByText('What needs to change?')).toBeInTheDocument();
    expect(reviewDsr).not.toHaveBeenCalled();
  });

  it('requests a revision with the typed comment once confirmed', async () => {
    listDsr.mockResolvedValueOnce(page([dsrRow()]));
    listDsr.mockResolvedValueOnce(page([]));
    reviewDsr.mockResolvedValue(dsrRow({ status: 'revision_required' }));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /request revision/i }));
    await user.type(screen.getByLabelText('What needs to change?'), 'Please add the assignment note.');
    await user.click(screen.getByRole('button', { name: /request revision/i }));

    expect(reviewDsr).toHaveBeenCalledWith('dsr-1', 'revision_required', 'Please add the assignment note.');
  });

  it('cancelling the comment field returns to the plain actions without calling the API', async () => {
    listDsr.mockResolvedValue(page([dsrRow()]));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /^reject$/i }));
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(reviewDsr).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeInTheDocument();
  });

  it('rolls back visibly when a rejection fails, keeping the row and its error together', async () => {
    listDsr.mockResolvedValue(page([dsrRow()]));
    reviewDsr.mockRejectedValue(new ApiError(400, 'validation_error', 'Say why, so the trainer knows what to change.', 'req-3'));
    const user = userEvent.setup();
    render(<DsrQueue />);
    await waitFor(() => expect(screen.getByText('Tina Trainer')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /^reject$/i }));
    await user.type(screen.getByLabelText('Why is this being rejected?'), 'Never happened.');
    await user.click(screen.getByRole('button', { name: /^reject$/i }));

    await waitFor(() => expect(screen.getByText('Say why, so the trainer knows what to change.')).toBeInTheDocument());
    expect(screen.getByText('Tina Trainer')).toBeInTheDocument();
  });
});
