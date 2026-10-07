'use client';

import { useCallback, useEffect, useState } from 'react';

import { StatusActions, type StatusAction } from '@/components/status-actions';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError, fieldErrors } from '@/lib/api';
import { getPublishChecklist, setCourseStatus } from '@/lib/courses';
import { STATUS_LABEL, STATUS_PLAIN, STATUS_VARIANT } from '@/lib/course-labels';
import type { CourseDetail, PublishChecklist, PublishStatus } from '@/types/api';

const ACTIVATE: StatusAction<PublishStatus> = {
  target: 'published',
  label: 'Activate',
  title: 'Activate this course?',
  description:
    'It becomes active: listed in the catalogue for students to find and join. You can deactivate it again later.',
  variant: 'primary',
};
const SUBMIT: StatusAction<PublishStatus> = {
  target: 'in_review',
  label: 'Submit for review',
  title: 'Submit this course for review?',
  description: 'An owner or administrator will check it and activate it. Nothing changes for students yet.',
  variant: 'outline',
};
const DEACTIVATE: StatusAction<PublishStatus> = {
  target: 'draft',
  label: 'Deactivate',
  title: 'Deactivate this course?',
  description:
    'It leaves the catalogue and becomes inactive. Existing batches and enrolled students keep their access. You can activate it again later.',
  variant: 'outline',
};
const ARCHIVE: StatusAction<PublishStatus> = {
  target: 'archived',
  label: 'Archive',
  title: 'Archive this course?',
  description:
    'It is hidden everywhere, no new batch can be created on it, and students can no longer open its lessons. An administrator can restore it later, as inactive.',
  variant: 'destructive',
};
const RESTORE: StatusAction<PublishStatus> = {
  target: 'draft',
  label: 'Restore',
  title: 'Restore this course?',
  description: 'It comes back as inactive (a draft). Activate it afterwards to list it again.',
  variant: 'primary',
};
const BACK_TO_DRAFT: StatusAction<PublishStatus> = {
  target: 'draft',
  label: 'Send back to draft',
  title: 'Send this course back to draft?',
  description: 'It leaves the review queue and stays inactive until it is submitted again.',
  variant: 'outline',
};
const WITHDRAW: StatusAction<PublishStatus> = {
  target: 'draft',
  label: 'Withdraw from review',
  title: 'Withdraw this course from review?',
  description: 'It leaves the review queue and stays inactive until it is submitted again.',
  variant: 'outline',
};

/**
 * Which transitions to offer, and what to say before each one.
 *
 * The server owns the real transition table and re-checks every request; this
 * only decides which buttons to draw. `can_publish` comes from the server too —
 * an assigned editor is offered "Submit for review" where an owner is offered
 * "Activate".
 */
export function transitionsFor(course: CourseDetail): StatusAction<PublishStatus>[] {
  const { status, can_publish: canPublish } = course;

  if (status === 'draft') return canPublish ? [ACTIVATE, SUBMIT] : [SUBMIT];
  if (status === 'in_review') {
    return canPublish
      ? [{ ...ACTIVATE, title: 'Approve and activate this course?' }, BACK_TO_DRAFT]
      : [WITHDRAW];
  }
  if (status === 'published') return canPublish ? [DEACTIVATE, ARCHIVE] : [];
  return canPublish ? [RESTORE] : [];
}

export function PublishPanel({
  course,
  onChanged,
}: {
  course: CourseDetail;
  onChanged: () => void | Promise<void>;
}) {
  const [checklist, setChecklist] = useState<PublishChecklist | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [blockers, setBlockers] = useState<string[]>([]);
  const [isBusy, setIsBusy] = useState(false);

  const loadChecklist = useCallback(() => {
    getPublishChecklist(course.id)
      .then(setChecklist)
      .catch(() => setChecklist(null));
  }, [course.id]);

  useEffect(() => {
    loadChecklist();
  }, [loadChecklist]);

  async function onTransition(target: PublishStatus) {
    setIsBusy(true);
    setErrors({});
    setBlockers([]);
    try {
      await setCourseStatus(course.id, target);
      await onChanged();
      loadChecklist();
    } catch (cause) {
      if (cause instanceof ApiError && Array.isArray(cause.details?.status)) {
        // The publish checklist comes back as a list of specific blockers.
        setBlockers(cause.details.status as string[]);
      } else {
        setErrors(fieldErrors(cause));
      }
    } finally {
      setIsBusy(false);
    }
  }

  const transitions = transitionsFor(course);
  const plain = STATUS_PLAIN[course.status];

  return (
    <Card data-testid="course-publishing">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex-1">Status</CardTitle>
          <Badge variant={STATUS_VARIANT[course.status]} dot>
            {STATUS_LABEL[course.status]}
          </Badge>
        </div>
        <CardDescription>
          <span className="font-medium text-ink">{plain.label}.</span> {plain.meaning}{' '}
          {course.can_publish
            ? ''
            : 'You can edit this course and submit it for review; an owner or administrator activates it. '}
          Batches can be created and students enrolled at any stage except archived.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-3">
        {course.status === 'archived' ? (
          <Alert variant="warning" data-testid="course-archived-banner">
            <AlertTitle>This course is archived</AlertTitle>
            It is hidden from the catalogue, no new batch can be created on it, and its lessons are
            closed to students. {course.can_publish ? 'Restore it to bring it back as inactive.' : ''}
          </Alert>
        ) : null}

        {errors.__all__ || errors.status ? (
          <Alert variant="error">{errors.status ?? errors.__all__}</Alert>
        ) : null}

        {blockers.length > 0 ? (
          <Alert variant="warning" className="space-y-2">
            <AlertTitle>Not ready to publish</AlertTitle>
            <ul className="list-inside list-disc text-ink-muted">
              {blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </Alert>
        ) : checklist && !checklist.ready && course.status !== 'published' ? (
          <Alert variant="info" className="space-y-2">
            <AlertTitle>Before this course can be published</AlertTitle>
            <ul className="list-inside list-disc text-ink-muted">
              {checklist.blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </Alert>
        ) : null}

        <StatusActions
          actions={transitions}
          busy={isBusy}
          onConfirm={onTransition}
          emptyText="No status changes are available to you for this course."
        />
      </CardContent>
    </Card>
  );
}
