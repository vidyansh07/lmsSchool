import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ClassHeader, initialTopicSelection, SKIP_TOPIC_VALUE } from '@/components/teaching/class-header';
import type { SessionWithTopic } from '@/lib/dsr';
import type { Module } from '@/types/api';

function session(overrides: Partial<SessionWithTopic> = {}): SessionWithTopic {
  return {
    id: 'session-1',
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
    topic: '',
    location: 'Room 4',
    status: 'in_progress',
    cancellation_reason: '',
    attendance_taken_at: null,
    can_take_attendance: true,
    planned_lesson_id: 'lesson-1',
    planned_lesson_title: 'Introduction to shells',
    actual_lesson_id: null,
    actual_lesson_title: null,
    topic_status: 'planned',
    ...overrides,
  };
}

function moduleWithLessons(): Module[] {
  return [
    {
      id: 'module-1',
      title: 'Module 1: Shell basics',
      description: '',
      position: 1,
      status: 'published',
      is_visible: true,
      lessons: [
        {
          id: 'lesson-1',
          title: 'Introduction to shells',
          slug: 'intro',
          description: '',
          content_type: 'text',
          duration_minutes: 30,
          position: 1,
          status: 'published',
          is_preview: false,
          is_required: true,
          resource_count: 0,
        },
        {
          id: 'lesson-2',
          title: 'Piping and redirection',
          slug: 'piping',
          description: '',
          content_type: 'text',
          duration_minutes: 30,
          position: 2,
          status: 'published',
          is_preview: false,
          is_required: true,
          resource_count: 0,
        },
      ],
    },
  ];
}

describe('ClassHeader', () => {
  it('renders the batch, course, date and time', () => {
    render(
      <ClassHeader
        session={session()}
        attendanceTaken={false}
        topicSelection=""
        onTopicSelectionChange={vi.fn()}
        modules={[]}
      />,
    );
    expect(screen.getByText('Linux Essentials')).toBeInTheDocument();
    expect(screen.getByText(/Morning batch/)).toBeInTheDocument();
    expect(screen.getByText(/09:00–11:00/)).toBeInTheDocument();
  });

  it('renders fallbacks for missing course, batch and plan rather than blank fields', () => {
    render(
      <ClassHeader
        session={session({
          course_title: '',
          batch_name: '',
          planned_lesson_id: null,
          planned_lesson_title: null,
        })}
        attendanceTaken={false}
        topicSelection=""
        onTopicSelectionChange={vi.fn()}
        modules={[]}
      />,
    );
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0);
    expect(screen.getByText('No data')).toBeInTheDocument();
    expect(screen.queryByText('undefined')).not.toBeInTheDocument();
  });

  it('shows the planned lesson as the plan', () => {
    render(
      <ClassHeader
        session={session()}
        attendanceTaken={false}
        topicSelection=""
        onTopicSelectionChange={vi.fn()}
        modules={[]}
      />,
    );
    expect(screen.getByText(/Introduction to shells/)).toBeInTheDocument();
  });

  it('lists the course’s published lessons, grouped by module, plus the skip option', () => {
    render(
      <ClassHeader
        session={session()}
        attendanceTaken={false}
        topicSelection="lesson-1"
        onTopicSelectionChange={vi.fn()}
        modules={moduleWithLessons()}
      />,
    );
    const select = screen.getByLabelText('What was actually covered');
    expect(select).toHaveValue('lesson-1');
    expect(screen.getByRole('option', { name: 'Piping and redirection' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Nothing covered today (skip)' })).toHaveValue(SKIP_TOPIC_VALUE);
  });

  it('reports a change when a different lesson is chosen', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ClassHeader
        session={session()}
        attendanceTaken={false}
        topicSelection="lesson-1"
        onTopicSelectionChange={onChange}
        modules={moduleWithLessons()}
      />,
    );
    await user.selectOptions(screen.getByLabelText('What was actually covered'), 'lesson-2');
    expect(onChange).toHaveBeenCalledWith('lesson-2');
  });

  it('excludes lessons that are not published', () => {
    const modules = moduleWithLessons();
    modules[0]!.lessons[1]!.status = 'draft';
    render(
      <ClassHeader
        session={session()}
        attendanceTaken={false}
        topicSelection="lesson-1"
        onTopicSelectionChange={vi.fn()}
        modules={modules}
      />,
    );
    expect(screen.queryByRole('option', { name: 'Piping and redirection' })).not.toBeInTheDocument();
  });

  it('shows a "Register taken" badge only once the register has been marked', () => {
    const { rerender } = render(
      <ClassHeader
        session={session()}
        attendanceTaken={false}
        topicSelection=""
        onTopicSelectionChange={vi.fn()}
        modules={[]}
      />,
    );
    expect(screen.queryByText('Register taken')).not.toBeInTheDocument();

    rerender(
      <ClassHeader
        session={session()}
        attendanceTaken
        topicSelection=""
        onTopicSelectionChange={vi.fn()}
        modules={[]}
      />,
    );
    expect(screen.getByText('Register taken')).toBeInTheDocument();
  });

  it('offers "Not this class?" only when a handler is supplied', async () => {
    const user = userEvent.setup();
    const onChangeClass = vi.fn();
    const { rerender } = render(
      <ClassHeader
        session={session()}
        attendanceTaken={false}
        topicSelection=""
        onTopicSelectionChange={vi.fn()}
        modules={[]}
        onChangeClass={onChangeClass}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Not this class?' }));
    expect(onChangeClass).toHaveBeenCalledOnce();

    rerender(
      <ClassHeader
        session={session()}
        attendanceTaken={false}
        topicSelection=""
        onTopicSelectionChange={vi.fn()}
        modules={[]}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Not this class?' })).not.toBeInTheDocument();
  });
});

describe('initialTopicSelection', () => {
  it('defaults to the planned lesson when the class has not been recorded yet', () => {
    expect(initialTopicSelection(session())).toBe('lesson-1');
  });

  it('prefers the actual lesson once one has been recorded', () => {
    expect(
      initialTopicSelection(session({ actual_lesson_id: 'lesson-2', topic_status: 'completed' })),
    ).toBe('lesson-2');
  });

  it('maps a skipped topic to the skip sentinel', () => {
    expect(initialTopicSelection(session({ topic_status: 'skipped' }))).toBe(SKIP_TOPIC_VALUE);
  });

  it('is empty when there is no plan and nothing recorded', () => {
    expect(
      initialTopicSelection(session({ planned_lesson_id: null, planned_lesson_title: null })),
    ).toBe('');
  });
});
