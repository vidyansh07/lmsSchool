import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { DSR } from '@/lib/dsr';
import type { BatchDetail, ClassSession, Register, RegisterEntry } from '@/types/api';
import type { SessionWithTopic } from '@/lib/dsr';

// --- Mocks -------------------------------------------------------------
//
// `@/lib/dsr` is partially mocked: the network-calling functions are test
// doubles, but `readDsrDraft` / `writeDsrDraft` / `clearDsrDraft` and
// `toWritePayload` are the real implementation, because the autosave and
// "survives a reload" tests below are only meaningful against the genuine
// `localStorage` read/write/try-catch behaviour.

const getRegister = vi.hoisted(() => vi.fn());
const markAttendance = vi.hoisted(() => vi.fn());
const listTodaySessions = vi.hoisted(() => vi.fn());
const listSessions = vi.hoisted(() => vi.fn());
vi.mock('@/lib/academics', () => ({ getRegister, markAttendance, listTodaySessions, listSessions }));

const getSessionWithTopic = vi.hoisted(() => vi.fn());
const getSessionDsr = vi.hoisted(() => vi.fn());
const startDsr = vi.hoisted(() => vi.fn());
const updateDsr = vi.hoisted(() => vi.fn());
const recordTopic = vi.hoisted(() => vi.fn());
vi.mock('@/lib/dsr', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/dsr')>();
  return { ...actual, getSessionWithTopic, getSessionDsr, startDsr, updateDsr, recordTopic };
});

const getBatch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', () => ({ getBatch }));

const listModules = vi.hoisted(() => vi.fn());
vi.mock('@/lib/courses', () => ({ listModules }));

const mockRouter = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
const mockSearchParams = vi.hoisted(() => ({ value: new URLSearchParams() }));
vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockSearchParams.value,
}));

import { ClassWorkspace, TodayWorkspace } from '@/app/teaching/today/page';

// --- Fixtures ------------------------------------------------------------

function registerEntry(overrides: Partial<RegisterEntry> = {}): RegisterEntry {
  return {
    enrollment_id: 'enrol-1',
    student_code: 'GRS-S-00001',
    full_name: 'Ada Lovelace',
    enrollment_status: 'active',
    status: null,
    note: '',
    was_corrected: false,
    ...overrides,
  };
}

function fixtures(overrides: {
  entries?: RegisterEntry[];
  canMark?: boolean;
  dsrId?: string | null;
  dsrStatus?: DSR['status'];
  isEditable?: boolean;
} = {}) {
  const entries = overrides.entries ?? [
    registerEntry({ enrollment_id: 'e1', full_name: 'Ada Lovelace', status: 'present' }),
    registerEntry({ enrollment_id: 'e2', full_name: 'Grace Hopper', status: 'present' }),
    registerEntry({ enrollment_id: 'e3', full_name: 'Alan Turing', status: 'absent' }),
  ];

  const session: SessionWithTopic = {
    id: 'session-1',
    batch_id: 'batch-1',
    batch_code: 'GRS-B-001',
    batch_name: 'Morning batch',
    course_title: 'Linux Essentials',
    session_date: '2026-09-01',
    start_time: '09:00:00',
    end_time: '11:00:00',
    timezone_name: 'Asia/Kolkata',
    starts_at: '2026-09-01T09:00:00+05:30',
    ends_at: '2026-09-01T11:00:00+05:30',
    duration_minutes: 120,
    trainer_name: 'Tina Trainer',
    topic: 'Shell basics',
    location: 'Room 4',
    status: 'completed',
    cancellation_reason: '',
    attendance_taken_at: '2026-09-01T11:05:00+05:30',
    can_take_attendance: true,
    planned_lesson_id: null,
    planned_lesson_title: null,
    actual_lesson_id: null,
    actual_lesson_title: null,
    topic_status: 'planned',
  };

  const register: Register = {
    session_id: session.id,
    session_date: session.session_date,
    batch_code: session.batch_code,
    can_mark: overrides.canMark ?? true,
    attendance_taken_at: session.attendance_taken_at,
    entries,
  };

  const dsr: DSR = {
    id: overrides.dsrId === undefined ? null : overrides.dsrId,
    session: session.id,
    session_date: session.session_date,
    batch: session.batch_id,
    batch_code: session.batch_code,
    trainer: 'trainer-1',
    trainer_code: 'GRS-T-001',
    trainer_name: 'Tina Trainer',
    report_date: session.session_date,
    start_time: session.start_time,
    end_time: session.end_time,
    module: null,
    module_title: null,
    planned_topic: session.topic,
    actual_topic: session.topic,
    student_count: entries.length,
    present_count: entries.filter((e) => e.status === 'present').length,
    absent_count: entries.filter((e) => e.status === 'absent').length,
    online_count: 0,
    offline_count: 0,
    teaching_notes: '',
    issues: '',
    student_concerns: '',
    assignment_given: false,
    assessment_conducted: false,
    status: overrides.dsrStatus ?? 'draft',
    is_editable: overrides.isEditable ?? true,
    submitted_at: null,
    reviewed_at: null,
    reviewed_by: null,
    reviewed_by_name: null,
    manager_comments: '',
    created_at: null,
    updated_at: null,
  };

  const batch: BatchDetail = {
    id: session.batch_id,
    code: session.batch_code,
    name: session.batch_name,
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: session.course_title,
    course_slug: 'linux-essentials',
    trainer_name: session.trainer_name,
    start_date: '2026-01-01',
    end_date: '2026-12-01',
    capacity: 30,
    enrolled_count: entries.length,
    seats_available: 30 - entries.length,
    status: 'active',
    created_at: '2026-01-01',
    description: '',
    trainer_id: 'trainer-1',
    trainer_code: 'GRS-T-001',
    schedules: [],
    updated_at: '2026-01-01',
    can_manage: true,
    can_view_roster: true,
  };

  return { session, register, dsr, batch };
}

function wireHappyPath(state: ReturnType<typeof fixtures>) {
  getSessionWithTopic.mockResolvedValue(state.session);
  getRegister.mockResolvedValue(state.register);
  getSessionDsr.mockResolvedValue(state.dsr);
  getBatch.mockResolvedValue(state.batch);
  listModules.mockResolvedValue([]);
  markAttendance.mockResolvedValue({ created: 0, updated: 0, corrections: 0 });
  recordTopic.mockResolvedValue(state.session);
  startDsr.mockResolvedValue({ ...state.dsr, id: 'dsr-new', status: 'submitted', is_editable: false });
  updateDsr.mockResolvedValue({ ...state.dsr, status: 'submitted', is_editable: false });
}

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  getRegister.mockReset();
  markAttendance.mockReset();
  listTodaySessions.mockReset().mockResolvedValue([]);
  listSessions.mockReset().mockResolvedValue({
    count: 0,
    page: 1,
    page_size: 20,
    total_pages: 0,
    next: null,
    previous: null,
    results: [],
  });
  getSessionWithTopic.mockReset();
  getSessionDsr.mockReset();
  startDsr.mockReset();
  updateDsr.mockReset();
  recordTopic.mockReset();
  getBatch.mockReset();
  listModules.mockReset();
  mockRouter.replace.mockReset();
  mockSearchParams.value = new URLSearchParams();
});

describe('ClassWorkspace', () => {
  it('prefills the report’s counts from the register the trainer is marking', async () => {
    const state = fixtures();
    wireHappyPath(state);
    render(<ClassWorkspace sessionId="session-1" />);

    await waitFor(() => expect(screen.getByText('Register')).toBeInTheDocument());
    // 2 present (Ada, Grace), 1 absent (Alan) — computed live, not the
    // possibly-stale count on the fetched DSR object.
    const presentStat = screen.getByText('Present:').parentElement;
    expect(presentStat).toHaveTextContent('2');
  });

  it('shows an error with retry when the class fails to load', async () => {
    getSessionWithTopic.mockRejectedValue(new ApiError(500, 'error', 'Server exploded.', 'req-1'));
    getRegister.mockResolvedValue(fixtures().register);
    getSessionDsr.mockResolvedValue(fixtures().dsr);
    render(<ClassWorkspace sessionId="session-1" />);

    await waitFor(() => expect(screen.getByText('Server exploded.')).toBeInTheDocument());
  });

  it('renders a class with no students on the register cleanly', async () => {
    const state = fixtures({ entries: [] });
    wireHappyPath(state);
    render(<ClassWorkspace sessionId="session-1" />);

    await waitFor(() => expect(screen.getByText('No students on this register')).toBeInTheDocument());
    expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
  });

  it('lets a backdated, already partly-marked class be completed in one action', async () => {
    const user = userEvent.setup();
    const state = fixtures({ dsrId: null });
    wireHappyPath(state);
    render(<ClassWorkspace sessionId="session-1" />);

    await waitFor(() => expect(screen.getByRole('row', { name: /Ada Lovelace, Present/ })).toBeInTheDocument());
    // The catch-up class is already partly marked, from paper — the screen
    // does not force the trainer to redo it.
    expect(screen.getByRole('row', { name: /Alan Turing, Absent/ })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Finish class' }));

    await waitFor(() => expect(markAttendance).toHaveBeenCalledOnce());
    expect(startDsr).toHaveBeenCalledWith(
      'session-1',
      expect.objectContaining({ present_count: 2, absent_count: 1, student_count: 3, submit: true }),
    );
    await waitFor(() => expect(screen.getByText('Class complete')).toBeInTheDocument());
  });

  it('finishing sends the register, then the topic, then the report — in that order', async () => {
    const user = userEvent.setup();
    const state = fixtures({
      entries: [registerEntry({ enrollment_id: 'e1', full_name: 'Ada Lovelace' })],
    });
    wireHappyPath(state);
    const order: string[] = [];
    markAttendance.mockImplementation(async () => {
      order.push('register');
      return { created: 1, updated: 0, corrections: 0 };
    });
    startDsr.mockImplementation(async () => {
      order.push('report');
      return { ...state.dsr, id: 'dsr-new', status: 'submitted', is_editable: false };
    });

    render(<ClassWorkspace sessionId="session-1" />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Finish class' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Finish class' }));

    await waitFor(() => expect(order).toEqual(['register', 'report']));
  });

  it('stops before writing the report if the register fails to save', async () => {
    const user = userEvent.setup();
    const state = fixtures();
    wireHappyPath(state);
    markAttendance.mockRejectedValue(
      new ApiError(400, 'validation_error', 'Bad register.', 'req-2', { __all__: ['This class has not started yet.'] }),
    );

    render(<ClassWorkspace sessionId="session-1" />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Finish class' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Finish class' }));

    await waitFor(() => expect(screen.getByText('This class has not started yet.')).toBeInTheDocument());
    expect(startDsr).not.toHaveBeenCalled();
    expect(updateDsr).not.toHaveBeenCalled();
  });

  it('a report validation error from the backend lands on the right field', async () => {
    const user = userEvent.setup();
    const state = fixtures();
    wireHappyPath(state);
    startDsr.mockRejectedValue(
      new ApiError(400, 'validation_error', 'The submitted data is invalid.', 'req-3', {
        issues: ['That is too long.'],
      }),
    );

    render(<ClassWorkspace sessionId="session-1" />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Finish class' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Finish class' }));

    await waitFor(() => expect(screen.getByText('That is too long.')).toBeInTheDocument());
    const issuesField = screen.getByLabelText('Issues');
    expect(issuesField).toHaveAttribute('aria-invalid', 'true');
  });

  it('a report already sent for review is read-only, but the register stays correctable', async () => {
    const user = userEvent.setup();
    const state = fixtures({ dsrId: 'dsr-1', dsrStatus: 'submitted', isEditable: false });
    wireHappyPath(state);
    render(<ClassWorkspace sessionId="session-1" />);

    await waitFor(() => expect(screen.getByText('Submitted')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Finish class' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Topic for the report')).not.toBeInTheDocument();

    // The register itself is a different permission and stays usable.
    screen.getByRole('row', { name: /Alan Turing/ }).focus();
    await user.keyboard('p');
    expect(screen.getByRole('row', { name: /Alan Turing, Present/ })).toBeInTheDocument();
  });

  it('restores an in-progress draft after a simulated reload', async () => {
    const state = fixtures();
    wireHappyPath(state);
    const { unmount } = render(<ClassWorkspace sessionId="session-1" />);

    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByLabelText('Teaching notes')).toBeInTheDocument());
    await user.type(screen.getByLabelText('Teaching notes'), 'Ran a live demo.');
    await waitFor(() => expect(screen.getByLabelText('Teaching notes')).toHaveValue('Ran a live demo.'));

    unmount();

    render(<ClassWorkspace sessionId="session-1" />);
    await waitFor(() =>
      expect(screen.getByLabelText('Teaching notes')).toHaveValue('Ran a live demo.'),
    );
  });

  it('does not lose the page when localStorage throws (a private window)', async () => {
    vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(window.localStorage.__proto__, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const state = fixtures();
    wireHappyPath(state);
    const user = userEvent.setup();

    render(<ClassWorkspace sessionId="session-1" />);
    await waitFor(() => expect(screen.getByLabelText('Teaching notes')).toBeInTheDocument());
    await user.type(screen.getByLabelText('Teaching notes'), 'x');
    expect(screen.getByLabelText('Teaching notes')).toHaveValue('x');
  });

  it('does not fire the Finish-class shortcut while typing in a textarea', async () => {
    const user = userEvent.setup();
    const state = fixtures();
    wireHappyPath(state);
    render(<ClassWorkspace sessionId="session-1" />);

    await waitFor(() => expect(screen.getByLabelText('Issues')).toBeInTheDocument());
    await user.click(screen.getByLabelText('Issues'));
    await user.keyboard('{Control>}{Enter}{/Control}');

    expect(startDsr).not.toHaveBeenCalled();
    expect(updateDsr).not.toHaveBeenCalled();
  });

  it('the Finish-class shortcut does fire outside of a text field', async () => {
    const user = userEvent.setup();
    const state = fixtures();
    wireHappyPath(state);
    render(<ClassWorkspace sessionId="session-1" />);

    await waitFor(() => expect(screen.getByRole('button', { name: 'Finish class' })).toBeInTheDocument());
    screen.getByRole('row', { name: /Ada Lovelace/ }).focus();
    await user.keyboard('{Control>}{Enter}{/Control}');

    await waitFor(() => expect(markAttendance).toHaveBeenCalledOnce());
  });
});

describe('TodayWorkspace', () => {
  function todaySession(overrides: Partial<ClassSession> = {}): ClassSession {
    return {
      id: 'session-today',
      batch_id: 'batch-1',
      batch_code: 'GRS-B-001',
      batch_name: 'Morning batch',
      course_title: 'Linux Essentials',
      session_date: '2026-09-07',
      start_time: '09:00:00',
      end_time: '11:00:00',
      timezone_name: 'Asia/Kolkata',
      starts_at: '2026-09-07T09:00:00+05:30',
      ends_at: '2026-09-07T11:00:00+05:30',
      duration_minutes: 120,
      trainer_name: 'Tina Trainer',
      topic: 'Shell basics',
      location: 'Room 4',
      status: 'in_progress',
      cancellation_reason: '',
      attendance_taken_at: null,
      can_take_attendance: true,
      planned_lesson_id: null,
      planned_lesson_title: null,
      actual_lesson_id: null,
      actual_lesson_title: null,
      topic_status: 'planned',
      ...overrides,
    };
  }

  it('opens straight into the class when there is exactly one today', async () => {
    listTodaySessions.mockResolvedValue([todaySession()]);
    render(<TodayWorkspace />);

    await waitFor(() =>
      expect(mockRouter.replace).toHaveBeenCalledWith('/teaching/today?session=session-today'),
    );
  });

  it('shows a picker instead of guessing when there is more than one class today', async () => {
    listTodaySessions.mockResolvedValue([
      todaySession({ id: 's1', batch_code: 'GRS-B-001', topic: 'Batch A class' }),
      todaySession({ id: 's2', batch_code: 'GRS-B-002', topic: 'Batch B class' }),
    ]);
    render(<TodayWorkspace />);

    await waitFor(() => expect(screen.getByText('Batch A class')).toBeInTheDocument());
    expect(screen.getByText('Batch B class')).toBeInTheDocument();
    expect(mockRouter.replace).not.toHaveBeenCalled();
  });

  it('shows an empty state, with a way to catch up on another day, when nothing is scheduled today', async () => {
    listTodaySessions.mockResolvedValue([]);
    render(<TodayWorkspace />);

    await waitFor(() => expect(screen.getByText('No classes today')).toBeInTheDocument());
    expect(screen.getByLabelText('Date', { exact: false })).toBeInTheDocument();
  });

  it('goes straight to the workspace when a session id is already in the URL', async () => {
    mockSearchParams.value = new URLSearchParams('session=session-1');
    const state = fixtures();
    wireHappyPath(state);
    render(<TodayWorkspace />);

    await waitFor(() => expect(screen.getByText('Register')).toBeInTheDocument());
    expect(listTodaySessions).not.toHaveBeenCalled();
  });
});
