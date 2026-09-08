'use client';

/**
 * "Set one from here if they ran or gave one, without leaving."
 *
 * Two independent mini-forms, one field each beyond the title — due date for
 * an assignment, maximum marks for an assessment — because `title` is the
 * only field either backend write actually requires
 * (`AssignmentWriteSerializer` / `AssessmentWriteSerializer`); everything
 * else has a server-side default. A trainer who just wants to log "yes, I
 * gave one" without describing it can tick the box and move on — the box is
 * a DSR field (`assignment_given` / `assessment_conducted`) submitted with
 * the rest of the report regardless of whether a record gets created here.
 * Creating the record is the *extra* step for a trainer with a moment to
 * spare, not a requirement for finishing the class.
 */
import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { errorMessage } from '@/lib/api';
import { createAssessment } from '@/lib/assessments';
import { createAssignment } from '@/lib/assignments';

export interface ClassWorkPanelProps {
  batchId: string;
  /** `null` until the batch's course id has loaded — assignment creation is
   *  course-scoped, so the form stays disabled (not hidden) until then. */
  courseId: string | null;
  isLoadingCourse?: boolean;
  assignmentGiven: boolean;
  assessmentConducted: boolean;
  onToggleAssignmentGiven: (value: boolean) => void;
  onToggleAssessmentConducted: (value: boolean) => void;
}

function AssignmentQuickCreate({
  batchId,
  courseId,
  isLoadingCourse,
}: {
  batchId: string;
  courseId: string | null;
  isLoadingCourse: boolean;
}) {
  const [title, setTitle] = useState('');
  const [dueAt, setDueAt] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  async function submit() {
    if (!courseId || !title.trim()) return;
    setIsSaving(true);
    setError(null);
    try {
      const assignment = await createAssignment(courseId, {
        title: title.trim(),
        batch: batchId,
        due_at: dueAt ? new Date(dueAt).toISOString() : undefined,
      });
      setCreated(assignment.code);
      setTitle('');
      setDueAt('');
    } catch (cause) {
      setError(errorMessage(cause, 'Could not create the assignment.'));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="animate-rise-in space-y-2 border-t border-border pt-3">
      {created ? (
        <Alert variant="success" role="status">
          Assignment {created} created.{' '}
          <button type="button" className="underline" onClick={() => setCreated(null)}>
            Create another
          </button>
        </Alert>
      ) : (
        <>
          {error ? (
            <Alert variant="error" role="alert">
              {error}
            </Alert>
          ) : null}
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Assignment title" htmlFor="quick-assignment-title" className="flex-1 min-w-[12rem]">
              <Input value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field label="Due" htmlFor="quick-assignment-due">
              <Input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} />
            </Field>
            <Button
              type="button"
              size="sm"
              onClick={() => void submit()}
              disabled={!courseId || !title.trim() || isSaving}
            >
              {isSaving ? 'Creating…' : 'Create assignment'}
            </Button>
          </div>
          {!courseId ? (
            <p className="text-xs text-muted-foreground">
              {isLoadingCourse
                ? 'Loading the course this batch runs…'
                : 'Course details are unavailable right now — the flag above still saves with the report.'}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}

function AssessmentQuickCreate({ batchId }: { batchId: string }) {
  const [title, setTitle] = useState('');
  const [maxMarks, setMaxMarks] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  async function submit() {
    if (!title.trim()) return;
    setIsSaving(true);
    setError(null);
    try {
      const assessment = await createAssessment(batchId, {
        title: title.trim(),
        category: 'weekly_test',
        max_marks: maxMarks.trim() || undefined,
      });
      setCreated(assessment.code);
      setTitle('');
      setMaxMarks('');
    } catch (cause) {
      setError(errorMessage(cause, 'Could not create the assessment.'));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="animate-rise-in space-y-2 border-t border-border pt-3">
      {created ? (
        <Alert variant="success" role="status">
          Assessment {created} created.{' '}
          <button type="button" className="underline" onClick={() => setCreated(null)}>
            Create another
          </button>
        </Alert>
      ) : (
        <>
          {error ? (
            <Alert variant="error" role="alert">
              {error}
            </Alert>
          ) : null}
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Assessment title" htmlFor="quick-assessment-title" className="flex-1 min-w-[12rem]">
              <Input value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field label="Max marks" htmlFor="quick-assessment-marks">
              <Input
                type="number"
                inputMode="decimal"
                min={0}
                className="w-24"
                value={maxMarks}
                onChange={(event) => setMaxMarks(event.target.value)}
              />
            </Field>
            <Button type="button" size="sm" onClick={() => void submit()} disabled={!title.trim() || isSaving}>
              {isSaving ? 'Creating…' : 'Create assessment'}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

export function ClassWorkPanel({
  batchId,
  courseId,
  isLoadingCourse = false,
  assignmentGiven,
  assessmentConducted,
  onToggleAssignmentGiven,
  onToggleAssessmentConducted,
}: ClassWorkPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Assessment &amp; assignment</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 rounded border-border accent-primary"
            checked={assignmentGiven}
            onChange={(event) => onToggleAssignmentGiven(event.target.checked)}
          />
          An assignment was given today
        </label>
        {assignmentGiven ? (
          <AssignmentQuickCreate batchId={batchId} courseId={courseId} isLoadingCourse={isLoadingCourse} />
        ) : null}

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 rounded border-border accent-primary"
            checked={assessmentConducted}
            onChange={(event) => onToggleAssessmentConducted(event.target.checked)}
          />
          A test or assessment was conducted today
        </label>
        {assessmentConducted ? <AssessmentQuickCreate batchId={batchId} /> : null}
      </CardContent>
    </Card>
  );
}
