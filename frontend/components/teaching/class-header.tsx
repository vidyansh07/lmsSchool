'use client';

/**
 * The class at a glance, plus the one control this screen owes the
 * curriculum: confirming what was actually covered.
 *
 * "The planned lesson is shown; recording what was actually covered is one
 * control, defaulted to the plan" (the brief) maps directly onto the backend:
 * `session.planned_lesson_title` is the plan, and `POST .../topic/` is the
 * one endpoint that records the actual lesson. The control here is a single
 * `<select>` — native, so arrow keys and type-ahead work for free — whose
 * value already defaults to the planned lesson (or the "skip" option when
 * there is no plan to default to). It does not save on every change: saving
 * happens once, as part of "Finish class" (see the workspace), so a trainer
 * whose class matched the plan does not need to touch this control at all —
 * confirming happens by doing nothing, which is the point.
 */
import { useId } from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/input';
import { SESSION_STATUS_LABEL, SESSION_STATUS_VARIANT } from '@/lib/academic-labels';
import { formatClassTime, type SessionWithTopic } from '@/lib/dsr';
import { fallback, formatDate, NO_DATA } from '@/lib/format';
import type { Module } from '@/types/api';

/** Sentinel for "nothing was covered" — kept out of the UUID space so it can
 *  never collide with a real lesson id. */
export const SKIP_TOPIC_VALUE = '__skipped__';

export interface ClassHeaderProps {
  session: SessionWithTopic;
  /** Register-taken state, shown as a badge — passed in rather than read off
   *  `session` because the workspace refreshes it independently of the
   *  session record. */
  attendanceTaken: boolean;
  topicSelection: string;
  onTopicSelectionChange: (value: string) => void;
  modules: Module[];
  isLoadingModules?: boolean;
  onChangeClass?: () => void;
}

export function ClassHeader({
  session,
  attendanceTaken,
  topicSelection,
  onTopicSelectionChange,
  modules,
  isLoadingModules = false,
  onChangeClass,
}: ClassHeaderProps) {
  const topicFieldId = useId();
  const groups = modules
    .map((module) => ({
      module,
      lessons: module.lessons.filter((lesson) => lesson.status === 'published'),
    }))
    .filter((group) => group.lessons.length > 0);

  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={SESSION_STATUS_VARIANT[session.status]}>
              {SESSION_STATUS_LABEL[session.status]}
            </Badge>
            {attendanceTaken ? <Badge variant="success">Register taken</Badge> : null}
            <span className="font-mono text-xs text-muted-foreground">
              {fallback(session.batch_code)}
            </span>
          </div>
          {onChangeClass ? (
            <button
              type="button"
              onClick={onChangeClass}
              className="text-xs font-medium text-primary underline-offset-2 hover:underline"
            >
              Not this class?
            </button>
          ) : null}
        </div>
        <CardTitle>{fallback(session.course_title)}</CardTitle>
        <CardDescription>
          {fallback(session.batch_name)} · {formatDate(session.session_date)} ·{' '}
          {formatClassTime(session.start_time)}–{formatClassTime(session.end_time)}
          {session.location ? ` · ${session.location}` : ''}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm">
          <span className="text-muted-foreground">Plan: </span>
          {fallback(session.planned_lesson_title, NO_DATA)}
        </p>

        <Field label="What was actually covered" htmlFor={topicFieldId}>
          <Select
            value={topicSelection}
            disabled={isLoadingModules}
            onChange={(event) => onTopicSelectionChange(event.target.value)}
          >
            {!session.planned_lesson_id ? (
              <option value="">Choose what this class covered…</option>
            ) : null}
            {groups.map(({ module, lessons }) => (
              <optgroup key={module.id} label={fallback(module.title)}>
                {lessons.map((lesson) => (
                  <option key={lesson.id} value={lesson.id}>
                    {lesson.title}
                  </option>
                ))}
              </optgroup>
            ))}
            <option value={SKIP_TOPIC_VALUE}>Nothing covered today (skip)</option>
          </Select>
        </Field>
      </CardContent>
    </Card>
  );
}

/** The lesson id / skip-sentinel a class's current topic state maps to —
 *  the workspace uses this to seed `topicSelection` on load. */
export function initialTopicSelection(session: SessionWithTopic): string {
  if (session.topic_status === 'skipped') return SKIP_TOPIC_VALUE;
  return session.actual_lesson_id ?? session.planned_lesson_id ?? '';
}
