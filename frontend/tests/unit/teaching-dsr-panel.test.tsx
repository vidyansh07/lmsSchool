import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { DsrPanel } from '@/components/teaching/dsr-panel';
import type { DSR, DSRWritePayload } from '@/lib/dsr';

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
