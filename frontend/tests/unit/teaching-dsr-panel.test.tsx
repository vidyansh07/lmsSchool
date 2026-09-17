import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DsrPanel } from '@/components/teaching/dsr-panel';
import { ApiError } from '@/lib/api';
import type { DSR, DSRWritePayload } from '@/lib/dsr';
import type { ActivityDetail, DsrHistoryEntry, RosterEntry } from '@/types/api';

const getBatchRoster = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, getBatchRoster };
});

const listActivityTypes = vi.hoisted(() => vi.fn());
vi.mock('@/lib/work', async () => {
  const actual = await vi.importActual<typeof import('@/lib/work')>('@/lib/work');
  return { ...actual, listActivityTypes };
});

const createActivityFromDsr = vi.hoisted(() => vi.fn());
const getDsrHistory = vi.hoisted(() => vi.fn());
vi.mock('@/lib/dsr', async () => {
  const actual = await vi.importActual<typeof import('@/lib/dsr')>('@/lib/dsr');
  return { ...actual, createActivityFromDsr, getDsrHistory };
});

function dsr(overrides: Partial<DSR> = {}): DSR {
  return {
    id: null,
    session: 'session-1',
    session_date: '2026-09-07',
    batch: 'batch-1',
    batch_code: 'GRS-B-001',
    trainer: 'trainer-1',
    trainer_code: 'GRS-T-001',
    trainer_name: 'Tina Trainer',
    report_date: '2026-09-07',
    start_time: '09:00:00',
    end_time: '11:00:00',
    module: null,
    module_title: null,
    planned_topic: 'Linux basics',
    actual_topic: 'Linux basics',
    student_count: 0,
    present_count: 0,
    absent_count: 0,
    online_count: 0,
    offline_count: 0,
    teaching_notes: '',
    issues: '',
    student_concerns: '',
    assignment_given: false,
    assessment_conducted: false,
    status: 'draft',
    is_editable: true,
    submitted_at: null,
    reviewed_at: null,
    reviewed_by: null,
    reviewed_by_name: null,
    manager_comments: '',
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function draftFrom(source: DSR): DSRWritePayload {
  return {
    actual_topic: source.actual_topic,
    teaching_notes: source.teaching_notes,
    issues: source.issues,
    student_concerns: source.student_concerns,
    online_count: source.online_count,
    offline_count: source.offline_count,
    assignment_given: source.assignment_given,
    assessment_conducted: source.assessment_conducted,
  };
}

function renderPanel(overrides: {
  dsrOverrides?: Partial<DSR>;
  draftOverrides?: DSRWritePayload;
  onChange?: (patch: DSRWritePayload) => void;
  fieldErrors?: Record<string, string>;
  presentCount?: number;
  absentCount?: number;
  studentCount?: number;
  isDirty?: boolean;
  isSavingDraft?: boolean;
  lastSavedAt?: string | null;
} = {}) {
  const record = dsr(overrides.dsrOverrides);
  const onChange = overrides.onChange ?? vi.fn();
  render(
    <DsrPanel
      dsr={record}
      draft={overrides.draftOverrides ?? draftFrom(record)}
      onChange={onChange}
      presentCount={overrides.presentCount ?? 0}
      absentCount={overrides.absentCount ?? 0}
      studentCount={overrides.studentCount ?? 0}
      fieldErrors={overrides.fieldErrors ?? {}}
      isDirty={overrides.isDirty ?? false}
      isSavingDraft={overrides.isSavingDraft ?? false}
      lastSavedAt={overrides.lastSavedAt ?? null}
    />,
  );
  return { onChange, record };
}

function rosterEntry(overrides: Partial<RosterEntry> = {}): RosterEntry {
  return {
    id: 'enrollment-1',
    code: 'ENR-1',
    student_id: 'student-1',
    student_code: 'GRS-S-001',
    full_name: 'Sam Student',
    email: 'sam@example.com',
    status: 'active',
    enrolled_at: '2026-01-01',
    ...overrides,
  };
}

function activityDetail(overrides: Partial<ActivityDetail> = {}): ActivityDetail {
  return {
    id: 'activity-1',
    title: 'Mentoring session',
    status: 'planned',
    priority: 'normal',
    planned_at: null,
    due_at: null,
    completed_at: null,
    created_at: '2026-09-07T10:00:00Z',
    student: { id: 'student-1', name: 'Sam Student', student_id: 'GRS-S-001' },
    type: { id: 'type-1', slug: 'mentoring', name: 'Mentoring', category: 'mentoring' },
    batch: null,
    assigned_to: null,
    created_by: null,
    counts: { history: 0 },
    performed_by: null,
    reviewed_by: null,
    started_at: null,
    reviewed_at: null,
    duration_minutes: null,
    result: 'n/a',
    score: null,
    max_score: null,
    summary: '',
    review_note: '',
    student_visible: false,
    form: null,
    form_values: {},
    history: [],
    parent: null,
    children: [],
    automation_run: null,
    ...overrides,
  };
}

beforeEach(() => {
  getBatchRoster.mockReset().mockResolvedValue([rosterEntry()]);
  listActivityTypes.mockReset().mockResolvedValue({
    results: [{ id: 'type-1', slug: 'mentoring', name: 'Mentoring', category: 'mentoring' }],
  });
  createActivityFromDsr.mockReset();
  getDsrHistory.mockReset().mockResolvedValue([]);
});

describe('DsrPanel — editable draft', () => {
  it('shows the live counts passed in as props, not a stale snapshot on the DSR object', () => {
    renderPanel({ dsrOverrides: { present_count: 999 }, presentCount: 18, absentCount: 2, studentCount: 20 });
    expect(screen.getByText('18')).toBeInTheDocument();
    expect(screen.queryByText('999')).not.toBeInTheDocument();
  });

  it('edits the topic field through onChange', async () => {
    const user = userEvent.setup();
    const { onChange } = renderPanel();
    // One keystroke, checked against the field's known starting value —
    // `Input` is a controlled field with a static mock `onChange` here, so
    // (as with a real, unmocked controlled input) React re-asserts its
    // current `value` between keystrokes; typing a whole word onto it would
    // just re-assert-and-append on every character rather than build a
    // string, which is a quirk of this test double, not of the component.
    await user.type(screen.getByLabelText('Topic for the report'), '!');
    expect(onChange).toHaveBeenCalledWith({ actual_topic: 'Linux basics!' });
  });

  it('"All in person" fills offline with the present count and zeroes online', async () => {
    const user = userEvent.setup();
    const { onChange } = renderPanel({ presentCount: 15 });
    await user.click(screen.getByRole('button', { name: 'All in person' }));
    expect(onChange).toHaveBeenCalledWith({ offline_count: 15, online_count: 0 });
  });

  it('"All online" fills online with the present count and zeroes offline', async () => {
    const user = userEvent.setup();
    const { onChange } = renderPanel({ presentCount: 15 });
    await user.click(screen.getByRole('button', { name: 'All online' }));
    expect(onChange).toHaveBeenCalledWith({ online_count: 15, offline_count: 0 });
  });

  it('typing in teaching notes, issues and student concerns each reports its own field', async () => {
    const user = userEvent.setup();
    const { onChange } = renderPanel();

    await user.type(screen.getByLabelText('Teaching notes'), 'x');
    expect(onChange).toHaveBeenCalledWith({ teaching_notes: 'x' });

    await user.type(screen.getByLabelText('Issues'), 'y');
    expect(onChange).toHaveBeenCalledWith({ issues: 'y' });

    await user.type(screen.getByLabelText('Student concerns'), 'z');
    expect(onChange).toHaveBeenCalledWith({ student_concerns: 'z' });
  });

  it('attaches a field error to the right input', () => {
    renderPanel({ fieldErrors: { issues: 'Too long.' } });
    const issuesField = screen.getByLabelText('Issues');
    expect(issuesField).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Too long.')).toBeInTheDocument();
  });

  it('renders null/blank draft fields as empty inputs rather than "undefined"', () => {
    renderPanel({ draftOverrides: {} });
    expect(screen.getByLabelText('Topic for the report')).toHaveValue('');
    expect(screen.getByLabelText('Teaching notes')).toHaveValue('');
    expect(screen.queryByText('undefined')).not.toBeInTheDocument();
  });

  it('shows a revision-required notice with the manager’s comments', () => {
    renderPanel({
      dsrOverrides: { status: 'revision_required', manager_comments: 'Please add attendance detail.' },
    });
    expect(screen.getByText(/Please add attendance detail\./)).toBeInTheDocument();
  });

  describe('draft status line', () => {
    it('reads "Unsaved changes" while dirty', () => {
      renderPanel({ isDirty: true });
      expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    });

    it('reads "Saving draft…" while a save is in flight', () => {
      renderPanel({ isSavingDraft: true });
      expect(screen.getByText('Saving draft…')).toBeInTheDocument();
    });

    it('reads the saved time once clean', () => {
      renderPanel({ lastSavedAt: '2026-09-07T09:30:00Z', isDirty: false });
      expect(screen.getByText(/Draft saved/)).toBeInTheDocument();
    });
  });
});

describe('DsrPanel — no longer editable', () => {
  it('renders a read-only summary instead of a form once the report has moved past draft', () => {
    renderPanel({ dsrOverrides: { status: 'approved', is_editable: false } });
    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.queryByLabelText('Topic for the report')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'All in person' })).not.toBeInTheDocument();
  });

  it('shows the rejection reason on a rejected report', () => {
    renderPanel({
      dsrOverrides: { status: 'rejected', is_editable: false, manager_comments: 'Numbers do not add up.' },
    });
    expect(screen.getByText('Numbers do not add up.')).toBeInTheDocument();
  });

  it('falls back cleanly when a locked report has no topic recorded', () => {
    renderPanel({ dsrOverrides: { status: 'submitted', is_editable: false, actual_topic: '' } });
    expect(screen.getByText('No data')).toBeInTheDocument();
  });
});

describe('DsrPanel — follow-up (create activity, history)', () => {
  it('offers neither action for an unsaved preview with no id yet', () => {
    renderPanel({ dsrOverrides: { id: null } });
    expect(screen.queryByRole('button', { name: 'Create activity from this class' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'View history' })).not.toBeInTheDocument();
  });

  it('validates student and activity type before submitting', async () => {
    const user = userEvent.setup();
    renderPanel({ dsrOverrides: { id: 'dsr-1' } });

    await user.click(screen.getByRole('button', { name: 'Create activity from this class' }));
    await waitFor(() => expect(getBatchRoster).toHaveBeenCalledWith('batch-1'));
    await user.click(screen.getByRole('button', { name: 'Create activity' }));

    expect(screen.getByText('Choose a student.')).toBeInTheDocument();
    expect(screen.getByText('Choose an activity type.')).toBeInTheDocument();
    expect(createActivityFromDsr).not.toHaveBeenCalled();
  });

  it('creates the activity and shows a link to it on success', async () => {
    const user = userEvent.setup();
    createActivityFromDsr.mockResolvedValue(activityDetail());
    renderPanel({ dsrOverrides: { id: 'dsr-1' } });

    await user.click(screen.getByRole('button', { name: 'Create activity from this class' }));
    await waitFor(() => expect(screen.getByRole('option', { name: /Sam Student/ })).toBeInTheDocument());

    // `Field`'s required asterisk (`ui/field.tsx`) is part of the label's
    // own accessible name with no separating space, and the panel's other
    // "Student concerns" field would also match a plain `exact: false`
    // lookup for "Student" — the literal trailing `*` is the simplest
    // unambiguous match.
    await user.selectOptions(screen.getByLabelText('Student*'), 'student-1');
    await user.selectOptions(screen.getByLabelText('Activity type*'), 'mentoring');
    await user.click(screen.getByRole('button', { name: 'Create activity' }));

    expect(createActivityFromDsr).toHaveBeenCalledWith('dsr-1', {
      student: 'student-1',
      activity_type: 'mentoring',
      title: undefined,
      due_in_days: undefined,
    });
    await waitFor(() => expect(screen.getByText('Activity created.')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: 'Mentoring session' })).toHaveAttribute(
      'href',
      '/activities?id=activity-1',
    );
  });

  it('surfaces a server error on a failed submission without losing the picked values', async () => {
    const user = userEvent.setup();
    createActivityFromDsr.mockRejectedValue(
      new ApiError(400, 'validation_error', 'Could not create the activity.', 'req-1'),
    );
    renderPanel({ dsrOverrides: { id: 'dsr-1' } });

    await user.click(screen.getByRole('button', { name: 'Create activity from this class' }));
    await waitFor(() => expect(screen.getByRole('option', { name: /Sam Student/ })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Student*'), 'student-1');
    await user.selectOptions(screen.getByLabelText('Activity type*'), 'mentoring');
    await user.click(screen.getByRole('button', { name: 'Create activity' }));

    await waitFor(() => expect(screen.getByText('Could not create the activity.')).toBeInTheDocument());
    expect(screen.getByLabelText('Student*')).toHaveValue('student-1');
  });

  it('renders a mixed history — an edit and a rejection with its comment visible', async () => {
    const user = userEvent.setup();
    const entries: DsrHistoryEntry[] = [
      {
        id: 'h-2',
        action: 'dsr.rejected',
        actor: { id: 'mgr-1', name: 'Mira Manager' },
        context: { from: 'submitted', to: 'rejected', comments: 'Attendance numbers do not add up.' },
        created_at: '2026-09-07T12:00:00Z',
      },
      {
        id: 'h-1',
        action: 'dsr.updated',
        actor: { id: 'trainer-1', name: 'Tina Trainer' },
        context: { changes: { actual_topic: { from: 'Linux basics', to: 'Linux basics, day 2' } } },
        created_at: '2026-09-07T09:15:00Z',
      },
    ];
    getDsrHistory.mockResolvedValue(entries);
    renderPanel({ dsrOverrides: { id: 'dsr-1' } });

    await user.click(screen.getByRole('button', { name: 'View history' }));
    await waitFor(() => expect(getDsrHistory).toHaveBeenCalledWith('dsr-1'));

    expect(await screen.findByText('Rejected')).toBeInTheDocument();
    expect(screen.getByText('Mira Manager', { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Attendance numbers do not add up\./)).toBeInTheDocument();
    expect(screen.getByText('Report updated')).toBeInTheDocument();
    expect(screen.getByText(/Linux basics → Linux basics, day 2/)).toBeInTheDocument();
  });

  it('renders an empty history state cleanly', async () => {
    const user = userEvent.setup();
    getDsrHistory.mockResolvedValue([]);
    renderPanel({ dsrOverrides: { id: 'dsr-1' } });

    await user.click(screen.getByRole('button', { name: 'View history' }));
    expect(await screen.findByText('No changes recorded yet.')).toBeInTheDocument();
  });
});
