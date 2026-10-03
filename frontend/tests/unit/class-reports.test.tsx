import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BatchClassReports } from '@/components/manage/batch-class-reports';
import { ClassNotesPanel } from '@/components/student/class-notes-panel';
import { ReportsToFill } from '@/components/teaching/reports-to-fill';
import type { BatchReportSummary, MissingReportRow, StudentClassNote } from '@/lib/dsr';

const useApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi }));

const listMissingReports = vi.hoisted(() => vi.fn());
vi.mock('@/lib/dsr', async () => {
  const actual = await vi.importActual<typeof import('@/lib/dsr')>('@/lib/dsr');
  return { ...actual, listMissingReports };
});

function loaded<T>(data: T) {
  return { data, error: null, isLoading: false, reload: vi.fn() };
}

function missing(overrides: Partial<MissingReportRow> = {}): MissingReportRow {
  return {
    session: 'session-1',
    date: '2026-10-02',
    start_time: '09:00:00',
    end_time: '11:00:00',
    batch: 'batch-1',
    batch_code: 'GRS-B-001',
    trainer_name: 'Tina Trainer',
    dsr: null,
    dsr_status: null,
    due_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  useApi.mockReset();
  listMissingReports.mockReset();
});

describe('ReportsToFill', () => {
  it('lists each class without a report, linking to it', async () => {
    listMissingReports.mockResolvedValue([missing()]);
    render(<ReportsToFill />);
    await waitFor(() => expect(screen.getByText('Reports to fill')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: 'Fill in' })).toHaveAttribute(
      'href',
      '/teaching/today?session=session-1',
    );
  });

  it('marks a report past its deadline as overdue', async () => {
    listMissingReports.mockResolvedValue([missing({ due_at: '2020-01-01T00:00:00Z', dsr: 'dsr-1' })]);
    render(<ReportsToFill />);
    await waitFor(() => expect(screen.getByText('Overdue')).toBeInTheDocument());
  });

  it('leaves out the class already open, and renders nothing when that was the only one', async () => {
    listMissingReports.mockResolvedValue([missing()]);
    const { container } = render(<ReportsToFill exceptSessionId="session-1" />);
    await waitFor(() => expect(listMissingReports).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('stays quiet when the list cannot be loaded', async () => {
    listMissingReports.mockRejectedValue(new Error('down'));
    const { container } = render(<ReportsToFill />);
    await waitFor(() => expect(listMissingReports).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

function summary(overrides: Partial<BatchReportSummary> = {}): BatchReportSummary {
  return {
    batch: { id: 'batch-1', code: 'GRS-B-001' },
    days: 30,
    classes: [
      {
        session: 'session-1',
        date: '2026-10-01',
        start_time: '09:00:00',
        end_time: '11:00:00',
        trainer_name: 'Tina Trainer',
        state: 'submitted',
        dsr: 'dsr-1',
        topic: 'Permissions',
        lessons: ['Files and folders'],
        topic_status: 'completed',
        present: 10,
        absent: 2,
        student_notes: 1,
        homework: true,
      },
      {
        session: 'session-2',
        date: '2026-10-02',
        start_time: '09:00:00',
        end_time: '11:00:00',
        trainer_name: 'Tina Trainer',
        state: 'missing',
        dsr: null,
        topic: '',
        lessons: [],
        topic_status: null,
        present: null,
        absent: null,
        student_notes: 0,
        homework: false,
      },
    ],
    counts: { held: 2, submitted: 1, on_time: 1, missing: 1, overdue: 0 },
    coverage: {
      lessons_total: 10,
      lessons_covered: 3,
      percent: 30,
      next_lesson: { id: 'lesson-4', title: 'Users and groups' },
    },
    ...overrides,
  };
}

describe('BatchClassReports', () => {
  it('shows coverage, counts, each class and the export link', () => {
    useApi.mockReturnValue(loaded(summary()));
    render(<BatchClassReports batchId="batch-1" />);
    expect(screen.getByText('3 of 10 lessons')).toBeInTheDocument();
    expect(screen.getByText('Next up: Users and groups')).toBeInTheDocument();
    expect(screen.getByText(/Permissions · 10 present, 2 absent · 1 student note\(s\) · homework set/)).toBeInTheDocument();
    expect(screen.getByText('Not written')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /export csv/i })).toHaveAttribute(
      'href',
      expect.stringContaining('/api/v1/batches/batch-1/dsr-export/?days=30'),
    );
  });

  it('offers to read only the classes that have a report', () => {
    useApi.mockReturnValue(loaded(summary()));
    render(<BatchClassReports batchId="batch-1" />);
    expect(screen.getAllByRole('button', { name: /read the report/i })).toHaveLength(1);
  });

  it('shows an error with retry', () => {
    const reload = vi.fn();
    useApi.mockReturnValue({
      data: null,
      error: { message: 'Down.', requestId: 'req-1' },
      isLoading: false,
      reload,
    });
    render(<BatchClassReports batchId="batch-1" />);
    expect(screen.getByText('Down.')).toBeInTheDocument();
  });
});

function note(overrides: Partial<StudentClassNote> = {}): StudentClassNote {
  return {
    id: 'dsr-1',
    report_date: '2026-10-01',
    start_time: '09:00:00',
    batch_code: 'GRS-B-001',
    trainer_name: 'Tina Trainer',
    topic: 'Permissions',
    lessons_covered: [{ id: 'lesson-1', title: 'Files and folders', module: 'module-1' }],
    homework: 'Read chapter 4',
    homework_due_on: '2026-10-05',
    homework_assignment: null,
    homework_assignment_title: null,
    ...overrides,
  };
}

describe('ClassNotesPanel', () => {
  it('shows what was covered and the homework', () => {
    useApi.mockReturnValue(
      loaded({ count: 1, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results: [note()] }),
    );
    render(<ClassNotesPanel />);
    expect(screen.getByText('What we covered')).toBeInTheDocument();
    expect(screen.getByText('Permissions')).toBeInTheDocument();
    expect(screen.getByText('Files and folders')).toBeInTheDocument();
    expect(screen.getByText('Read chapter 4')).toBeInTheDocument();
  });

  it('renders nothing before any class has a report', () => {
    useApi.mockReturnValue(
      loaded({ count: 0, page: 1, page_size: 20, total_pages: 0, next: null, previous: null, results: [] }),
    );
    const { container } = render(<ClassNotesPanel />);
    expect(container).toBeEmptyDOMElement();
  });
});
