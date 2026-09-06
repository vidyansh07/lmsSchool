/**
 * "What do I owe" — the first thing a student should see.
 *
 * Assignments and projects are two different endpoints with two different
 * "still needs me" rules (an assignment is open for resubmission on a
 * returned attempt; a project's rule comes from `is_open_to_student` on the
 * work record itself), so this file mirrors the exact eligibility checks
 * `app/my-assignments/page.tsx` and `app/my-projects/page.tsx` already use for
 * their own submit buttons — a count here that disagreed with whether the
 * linked screen actually lets the student act would be worse than no count.
 *
 * Both computers are exported on their own so a test can assert the counting
 * rule directly, without mounting the panel and parsing rendered text.
 */
import { PendingActions, type PendingAction } from '@/components/pending-actions';
import type { StudentAssignment, StudentProject } from '@/types/api';

export interface WorkTally {
  count: number;
  /** How many of `count` are already past their due date. */
  overdueCount: number;
}

function isAssignmentOutstanding(assignment: StudentAssignment): boolean {
  const mine = assignment.my_submission;
  if (!assignment.is_open) return false;
  if (mine === null) return true;
  if (mine.status === 'returned') return true;
  return (
    assignment.allow_resubmission &&
    mine.status !== 'graded' &&
    mine.attempt < assignment.max_attempts
  );
}

/** Open assignments still needing a submission, and how many are overdue. */
export function tallyAssignments(assignments: StudentAssignment[]): WorkTally {
  const outstanding = assignments.filter(isAssignmentOutstanding);
  const now = Date.now();
  const overdueCount = outstanding.filter((assignment) => {
    const due = assignment.due_at ? Date.parse(assignment.due_at) : NaN;
    return Number.isFinite(due) && due < now;
  }).length;
  return { count: outstanding.length, overdueCount };
}

function isProjectOutstanding(project: StudentProject): boolean {
  if (!project.is_open) return false;
  const mine = project.my_work;
  if (mine === null) return true;
  if (!mine.is_open_to_student) return false;
  return mine.status !== 'submitted' && mine.status !== 'under_review' && mine.status !== 'approved' && mine.status !== 'completed';
}

/** Open project work still needing a hand-in, and how many are past their end date. */
export function tallyProjects(projects: StudentProject[]): WorkTally {
  const outstanding = projects.filter(isProjectOutstanding);
  const today = new Date().toISOString().slice(0, 10);
  const overdueCount = outstanding.filter(
    (project) => project.end_date !== null && project.end_date < today,
  ).length;
  return { count: outstanding.length, overdueCount };
}

export function PendingWorkPanel({
  assignments,
  projects,
  isLoading,
  error,
  onRetry,
}: {
  assignments: StudentAssignment[];
  projects: StudentProject[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  const assignmentTally = tallyAssignments(assignments);
  const projectTally = tallyProjects(projects);

  const items: PendingAction[] = [
    {
      id: 'assignments',
      label: 'assignment',
      count: assignmentTally.count,
      href: '/my-assignments',
      actionText: 'Hand in',
      urgent: assignmentTally.overdueCount > 0,
    },
    {
      id: 'projects',
      label: 'project',
      count: projectTally.count,
      href: '/my-projects',
      actionText: 'Hand in',
      urgent: projectTally.overdueCount > 0,
    },
  ];

  return (
    <PendingActions
      items={items}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      title="pending work"
      emptyTitle="Nothing outstanding"
      emptyDescription="Every assignment and project you have open is handed in."
    />
  );
}
