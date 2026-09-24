"use client";

/**
 * The activity detail drawer: history, the pinned form (read-only once
 * completed, editable while filling it in), the transition action bar, the
 * Complete form and the Review action.
 *
 * The transition bar renders only the buttons `lib/work.ts`'s
 * `legalTransitions(detail.status)` returns — never the whole lifecycle
 * table hardcoded here (there is no such field on the detail response
 * itself; see that function's own comment). Review is hidden entirely, not
 * merely disabled, when the signed-in user is the activity's performer or
 * assignee, mirroring the server's own refusal.
 */

import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { FieldRenderer } from "@/components/forms/field-renderer";
import { ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { ApiError, errorMessage, fieldErrors } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import { formatDateTime, formatDuration, NOT_ASSIGNED } from "@/lib/format";
import {
  ACTIVITY_CATEGORY_LABEL,
  ACTIVITY_PRIORITY_LABEL,
  ACTIVITY_STATUS_LABEL,
  ACTIVITY_STATUS_VARIANT,
  ACTIVITY_TRANSITION_LABEL,
  ACTIVITY_TRANSITION_REQUIRES_NOTE,
} from "@/lib/labels";
import {
  completeActivity,
  deleteActivity,
  getActivity,
  legalTransitions,
  reviewActivity,
  transitionActivity,
  updateActivity,
} from "@/lib/work";
import type { ActivityDetail, ActivityPriority, ActivityStatus } from "@/types/api";

const EDITABLE_STATUSES: ActivityStatus[] = ["draft", "planned", "assigned"];
const COMPLETABLE_STATUSES: ActivityStatus[] = ["assigned", "in_progress", "overdue"];

interface DetailState {
  key: string;
  detail: ActivityDetail | null;
  error: ApiError | null;
  isLoading: boolean;
}

function PersonLine({
  label,
  person,
}: {
  label: string;
  person: { id: string; name: string } | null;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="text-sm">{person ? person.name : NOT_ASSIGNED}</dd>
    </div>
  );
}

/** History rows, oldest first — the order a timeline reads naturally. */
function HistoryTimeline({ history }: { history: ActivityDetail["history"] }) {
  if (history.length === 0) {
    return <p className="text-sm text-ink-muted">No status changes yet.</p>;
  }
  return (
    <ol className="space-y-3 border-l border-line pl-4">
      {history.map((entry) => (
        <li key={entry.id} className="relative">
          <span className="absolute -left-[1.1rem] top-1.5 size-2 rounded-full bg-action" />
          <p className="text-sm font-medium">
            {entry.from_status ? (
              <>
                {ACTIVITY_STATUS_LABEL[entry.from_status]} →{" "}
                {ACTIVITY_STATUS_LABEL[entry.to_status]}
              </>
            ) : (
              ACTIVITY_STATUS_LABEL[entry.to_status]
            )}
          </p>
          <p className="text-xs text-ink-muted">
            {formatDateTime(entry.created_at)}
            {entry.actor ? ` · ${entry.actor.name}` : ""}
          </p>
          {entry.note ? <p className="mt-1 text-sm">{entry.note}</p> : null}
        </li>
      ))}
    </ol>
  );
}

export function ActivityDrawer({
  activityId,
  onOpenChange,
  onChanged,
}: {
  /** Null closes the sheet; a non-null id opens it and fetches that detail. */
  activityId: string | null;
  onOpenChange: (open: boolean) => void;
  /** Called after any mutation that a list row's own fields might reflect
   *  (a transition, a completion, a review, a delete) so the caller can
   *  reload the list behind the drawer. */
  onChanged: () => void;
}) {
  const { user } = useAuth();
  const [reloadToken, setReloadToken] = useState(0);
  // `reloadToken` lives inside the request identity (not just an effect
  // dependency) so a same-activity reload still resets `isLoading` to true
  // during render, the same shape `hooks/use-api.ts` uses.
  const key = `${activityId ?? ""}#${reloadToken}`;
  const [state, setState] = useState<DetailState>({
    key,
    detail: null,
    error: null,
    isLoading: Boolean(activityId),
  });
  if (state.key !== key) {
    setState({ key, detail: null, error: null, isLoading: Boolean(activityId) });
  }

  useEffect(() => {
    if (!activityId) return;
    let cancelled = false;
    getActivity(activityId)
      .then((detail) => {
        if (cancelled) return;
        setState({ key, detail, error: null, isLoading: false });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const apiError =
          cause instanceof ApiError
            ? cause
            : new ApiError(0, "unknown_error", "The request failed.", "");
        setState({ key, detail: null, error: apiError, isLoading: false });
      });
    return () => {
      cancelled = true;
    };
  }, [key, activityId]);

  const detail = state.detail;

  // --- Edit (title/planned_at/due_at/priority/assigned_to/student_visible) --
  const [editValues, setEditValues] = useState<{
    title: string;
    planned_at: string;
    due_at: string;
    priority: ActivityPriority;
    assigned_to: string;
    student_visible: boolean;
  } | null>(null);
  const [editForKey, setEditForKey] = useState<string | null>(null);
  const [editErrors, setEditErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  if (detail && editForKey !== `${detail.id}#${detail.status}`) {
    setEditValues({
      title: detail.title,
      planned_at: detail.planned_at ? detail.planned_at.slice(0, 16) : "",
      due_at: detail.due_at ? detail.due_at.slice(0, 16) : "",
      priority: detail.priority,
      assigned_to: detail.assigned_to?.id ?? "",
      student_visible: detail.student_visible,
    });
    setEditForKey(`${detail.id}#${detail.status}`);
    setEditErrors({});
  }

  // --- Transition (with a note dialog for cancel/reopen) --------------------
  const [transitioning, setTransitioning] = useState<ActivityStatus | null>(null);
  const [notePrompt, setNotePrompt] = useState<ActivityStatus | null>(null);
  const [noteValue, setNoteValue] = useState("");
  const [transitionError, setTransitionError] = useState<string | null>(null);

  // --- Complete ---------------------------------------------------------
  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [formValuesForKey, setFormValuesForKey] = useState<string | null>(null);
  const [summary, setSummary] = useState("");
  const [durationMinutes, setDurationMinutes] = useState("");
  const [completing, setCompleting] = useState(false);
  const [completeErrors, setCompleteErrors] = useState<Record<string, string>>({});

  if (detail && formValuesForKey !== detail.id) {
    setFormValues(detail.form_values);
    setSummary(detail.summary);
    setDurationMinutes(
      detail.duration_minutes !== null ? String(detail.duration_minutes) : "",
    );
    setCompleteErrors({});
    setFormValuesForKey(detail.id);
  }

  // --- Review -------------------------------------------------------------
  const [reviewNote, setReviewNote] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  // --- Delete ---------------------------------------------------------------
  const [deleteReason, setDeleteReason] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function reload() {
    setReloadToken((value) => value + 1);
  }

  async function saveEdit() {
    if (!detail || !editValues) return;
    setSaving(true);
    setEditErrors({});
    try {
      await updateActivity(detail.id, {
        title: editValues.title,
        planned_at: editValues.planned_at ? new Date(editValues.planned_at).toISOString() : null,
        due_at: editValues.due_at ? new Date(editValues.due_at).toISOString() : null,
        priority: editValues.priority,
        ...(editValues.assigned_to ? { assigned_to: editValues.assigned_to } : {}),
        // The server accepts only a hide (true → false), so this is never
        // sent as a re-reveal — the switch below cannot turn itself back on.
        ...(detail.student_visible && !editValues.student_visible
          ? { student_visible: false }
          : {}),
      });
      setNotice("Saved.");
      reload();
      onChanged();
    } catch (cause) {
      setEditErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  async function runTransition(to: ActivityStatus, note?: string) {
    if (!detail) return;
    setTransitioning(to);
    setTransitionError(null);
    try {
      await transitionActivity(detail.id, to, note);
      setNotePrompt(null);
      setNoteValue("");
      reload();
      onChanged();
    } catch (cause) {
      setTransitionError(errorMessage(cause, "Could not make that change."));
    } finally {
      setTransitioning(null);
    }
  }

  function onTransitionClick(to: ActivityStatus) {
    if (ACTIVITY_TRANSITION_REQUIRES_NOTE.has(to)) {
      setNotePrompt(to);
      setNoteValue("");
      return;
    }
    void runTransition(to);
  }

  async function submitComplete() {
    if (!detail) return;
    setCompleting(true);
    setCompleteErrors({});
    try {
      await completeActivity(detail.id, {
        form_values: formValues,
        summary: summary || undefined,
        duration_minutes: durationMinutes ? Number(durationMinutes) : undefined,
      });
      setNotice("Marked complete.");
      reload();
      onChanged();
    } catch (cause) {
      setCompleteErrors(fieldErrors(cause));
    } finally {
      setCompleting(false);
    }
  }

  async function submitReview(decision: "approved" | "requires_action") {
    if (!detail) return;
    if (decision === "requires_action" && !reviewNote.trim()) {
      setReviewError("A note is required to send this back.");
      return;
    }
    setReviewing(true);
    setReviewError(null);
    try {
      await reviewActivity(detail.id, decision, reviewNote.trim());
      setReviewNote("");
      setNotice(decision === "approved" ? "Approved." : "Sent back for action.");
      reload();
      onChanged();
    } catch (cause) {
      setReviewError(errorMessage(cause, "Could not record the review."));
    } finally {
      setReviewing(false);
    }
  }

  async function submitDelete() {
    if (!detail || !deleteReason.trim()) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteActivity(detail.id, deleteReason.trim());
      setDeleteOpen(false);
      onChanged();
      onOpenChange(false);
    } catch (cause) {
      setDeleteError(errorMessage(cause, "Could not delete this activity."));
    } finally {
      setDeleting(false);
    }
  }

  const isSelf =
    Boolean(user) &&
    Boolean(detail) &&
    (user!.id === detail!.performed_by?.id || user!.id === detail!.assigned_to?.id);

  const canReview =
    Boolean(detail) &&
    detail!.status === "under_review" &&
    can(user?.capabilities, Capability.activityReview) &&
    !isSelf;

  const isAssignee = Boolean(user) && Boolean(detail) && user!.id === detail!.assigned_to?.id;
  const isCreator = Boolean(user) && Boolean(detail) && user!.id === detail!.created_by?.id;

  // Mirrors `apps.work.access.can_complete`/`can_assign`: the backend also
  // authorizes the assignee/creator directly, per-record, rather than only
  // through a capability — a trainer holds none of the `activity.*`
  // capabilities (their reach is resolved per-record via
  // `_trainer_teaches_batch`), so gating on capability alone would hide
  // these actions from the exact person the backend lets perform them.
  const canComplete =
    Boolean(detail) &&
    COMPLETABLE_STATUSES.includes(detail!.status) &&
    (can(user?.capabilities, Capability.activityComplete) || isAssignee);

  const canEdit = Boolean(detail) && EDITABLE_STATUSES.includes(detail!.status);
  const canAssign = can(user?.capabilities, Capability.activityAssign) || isCreator;
  const canDelete = can(user?.capabilities, Capability.activityDelete);

  return (
    <Sheet open={Boolean(activityId)} onOpenChange={onOpenChange}>
      <SheetContent size="lg" className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{detail ? detail.title : "Activity"}</SheetTitle>
        </SheetHeader>

        {state.isLoading ? (
          <LoadingState label="Loading activity…" rows={6} />
        ) : state.error ? (
          <ErrorState
            title="Could not load this activity"
            message={state.error.message}
            requestId={state.error.requestId || undefined}
            onRetry={reload}
          />
        ) : !detail ? null : (
          <div className="space-y-6">
            {notice ? <Alert variant="success">{notice}</Alert> : null}

            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={ACTIVITY_STATUS_VARIANT[detail.status]}>
                {ACTIVITY_STATUS_LABEL[detail.status]}
              </Badge>
              <Badge variant="neutral">{ACTIVITY_PRIORITY_LABEL[detail.priority]}</Badge>
              <Badge variant="neutral">
                {ACTIVITY_CATEGORY_LABEL[detail.type.category]}
              </Badge>
            </div>

            <dl className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">
                  Student
                </dt>
                <dd className="text-sm">
                  {detail.student.name} · {detail.student.student_id}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Type</dt>
                <dd className="text-sm">{detail.type.name}</dd>
              </div>
              <PersonLine label="Assigned to" person={detail.assigned_to} />
              <PersonLine label="Created by" person={detail.created_by} />
              <PersonLine label="Performed by" person={detail.performed_by} />
              <PersonLine label="Reviewed by" person={detail.reviewed_by} />
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">
                  Planned
                </dt>
                <dd className="text-sm">{formatDateTime(detail.planned_at)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">Due</dt>
                <dd className="text-sm">{formatDateTime(detail.due_at)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">
                  Completed
                </dt>
                <dd className="text-sm">{formatDateTime(detail.completed_at)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-muted">
                  Duration
                </dt>
                <dd className="text-sm">
                  {detail.duration_minutes !== null
                    ? formatDuration(detail.duration_minutes)
                    : "Not recorded"}
                </dd>
              </div>
            </dl>

            {detail.summary ? (
              <div>
                <h3 className="text-sm font-semibold">Summary</h3>
                <p className="text-sm text-ink-muted">{detail.summary}</p>
              </div>
            ) : null}

            {detail.review_note ? (
              <Alert variant="warning">
                <p className="text-sm font-medium">Review note</p>
                <p className="text-sm">{detail.review_note}</p>
              </Alert>
            ) : null}

            {transitionError ? <Alert variant="error">{transitionError}</Alert> : null}

            {legalTransitions(detail.status).length > 0 ? (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">Change status</h3>
                <div className="flex flex-wrap gap-2">
                  {legalTransitions(detail.status).map((to) =>
                    ACTIVITY_TRANSITION_LABEL[to] ? (
                      <Button
                        key={to}
                        type="button"
                        size="sm"
                        variant={to === "cancelled" ? "destructive" : "outline"}
                        disabled={transitioning !== null}
                        onClick={() => onTransitionClick(to)}
                      >
                        {transitioning === to ? "Working…" : ACTIVITY_TRANSITION_LABEL[to]}
                      </Button>
                    ) : null,
                  )}
                </div>
              </div>
            ) : null}

            {canEdit ? (
              <div className="space-y-3 rounded-md border border-line p-3">
                <h3 className="text-sm font-semibold">Details</h3>
                {editValues ? (
                  <>
                    <Field label="Title" htmlFor="ad-title" error={editErrors.title}>
                      <Input
                        id="ad-title"
                        value={editValues.title}
                        onChange={(event) =>
                          setEditValues((current) =>
                            current ? { ...current, title: event.target.value } : current,
                          )
                        }
                      />
                    </Field>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field label="Planned at" htmlFor="ad-planned" error={editErrors.planned_at}>
                        <Input
                          id="ad-planned"
                          type="datetime-local"
                          value={editValues.planned_at}
                          onChange={(event) =>
                            setEditValues((current) =>
                              current
                                ? { ...current, planned_at: event.target.value }
                                : current,
                            )
                          }
                        />
                      </Field>
                      <Field label="Due at" htmlFor="ad-due" error={editErrors.due_at}>
                        <Input
                          id="ad-due"
                          type="datetime-local"
                          value={editValues.due_at}
                          onChange={(event) =>
                            setEditValues((current) =>
                              current ? { ...current, due_at: event.target.value } : current,
                            )
                          }
                        />
                      </Field>
                    </div>
                    <Field label="Priority" htmlFor="ad-priority" error={editErrors.priority}>
                      <Select
                        id="ad-priority"
                        value={editValues.priority}
                        onChange={(event) =>
                          setEditValues((current) =>
                            current
                              ? {
                                  ...current,
                                  priority: event.target.value as ActivityPriority,
                                }
                              : current,
                          )
                        }
                      >
                        {(["low", "normal", "high", "urgent"] as ActivityPriority[]).map(
                          (value) => (
                            <option key={value} value={value}>
                              {ACTIVITY_PRIORITY_LABEL[value]}
                            </option>
                          ),
                        )}
                      </Select>
                    </Field>
                    {canAssign ? (
                      <Field
                        label="Assigned to (user id)"
                        htmlFor="ad-assignee"
                        error={editErrors.assigned_to}
                        hint="The account this activity is assigned to."
                      >
                        <Input
                          id="ad-assignee"
                          value={editValues.assigned_to}
                          onChange={(event) =>
                            setEditValues((current) =>
                              current
                                ? { ...current, assigned_to: event.target.value }
                                : current,
                            )
                          }
                        />
                      </Field>
                    ) : null}
                    {detail.student_visible ? (
                      <div className="flex items-center justify-between rounded-md border border-line p-3">
                        <div>
                          <p className="text-sm font-medium">Visible to the student</p>
                          <p className="text-xs text-ink-muted">
                            Can only be turned off here, never back on.
                          </p>
                        </div>
                        <Switch
                          checked={editValues.student_visible}
                          onCheckedChange={(checked) =>
                            setEditValues((current) =>
                              current ? { ...current, student_visible: checked } : current,
                            )
                          }
                        />
                      </div>
                    ) : null}
                    {editErrors.__all__ ? (
                      <Alert variant="error">{editErrors.__all__}</Alert>
                    ) : null}
                    <div className="flex justify-end">
                      <Button type="button" size="sm" onClick={() => void saveEdit()} disabled={saving}>
                        {saving ? "Saving…" : "Save details"}
                      </Button>
                    </div>
                  </>
                ) : null}
              </div>
            ) : null}

            {canComplete ? (
              <div className="space-y-3 rounded-md border border-line p-3">
                <h3 className="text-sm font-semibold">Complete this activity</h3>
                {completeErrors.__all__ ? (
                  <Alert variant="error">{completeErrors.__all__}</Alert>
                ) : null}
                {detail.form ? (
                  <FieldRenderer
                    fields={detail.form.fields}
                    values={formValues}
                    errors={completeErrors}
                    onChange={(fieldKey, value) =>
                      setFormValues((current) => ({ ...current, [fieldKey]: value }))
                    }
                  />
                ) : (
                  <p className="text-sm text-ink-muted">
                    This type has no form — record a summary below.
                  </p>
                )}
                <Field label="Summary" htmlFor="ad-summary" error={completeErrors.summary}>
                  <Textarea
                    id="ad-summary"
                    value={summary}
                    onChange={(event) => setSummary(event.target.value)}
                  />
                </Field>
                <Field
                  label="Duration (minutes)"
                  htmlFor="ad-duration"
                  error={completeErrors.duration_minutes}
                >
                  <Input
                    id="ad-duration"
                    type="number"
                    min={0}
                    value={durationMinutes}
                    onChange={(event) => setDurationMinutes(event.target.value)}
                  />
                </Field>
                <div className="flex justify-end">
                  <Button type="button" size="sm" onClick={() => void submitComplete()} disabled={completing}>
                    {completing ? "Completing…" : "Mark complete"}
                  </Button>
                </div>
              </div>
            ) : null}

            {detail.form && !canComplete ? (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">Form</h3>
                {Object.keys(detail.form_values).length > 0 ? (
                  <FieldRenderer fields={detail.form.fields} values={detail.form_values} readOnly />
                ) : (
                  <p className="text-sm text-ink-muted">Not filled in yet.</p>
                )}
              </div>
            ) : null}

            {canReview ? (
              <div className="space-y-3 rounded-md border border-line p-3">
                <h3 className="text-sm font-semibold">Review</h3>
                {reviewError ? <Alert variant="error">{reviewError}</Alert> : null}
                <Field label="Note" htmlFor="ad-review-note" hint="Required when sending it back for action.">
                  <Textarea
                    id="ad-review-note"
                    value={reviewNote}
                    onChange={(event) => setReviewNote(event.target.value)}
                  />
                </Field>
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={reviewing}
                    onClick={() => void submitReview("requires_action")}
                  >
                    Requires action
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={reviewing}
                    onClick={() => void submitReview("approved")}
                  >
                    {reviewing ? "Working…" : "Approve"}
                  </Button>
                </div>
              </div>
            ) : null}

            <div className="space-y-2">
              <h3 className="text-sm font-semibold">History</h3>
              <HistoryTimeline history={detail.history} />
            </div>

            {canDelete ? (
              <div className="border-t border-line pt-4">
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={() => setDeleteOpen(true)}
                >
                  Delete activity
                </Button>
              </div>
            ) : null}
          </div>
        )}
      </SheetContent>

      <Dialog
        open={Boolean(notePrompt)}
        onOpenChange={(next) => (next ? undefined : setNotePrompt(null))}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {notePrompt ? ACTIVITY_TRANSITION_LABEL[notePrompt] : ""} this activity
            </DialogTitle>
            <DialogDescription>A reason is required for this change.</DialogDescription>
          </DialogHeader>
          <Field label="Reason" htmlFor="ad-transition-note" required>
            <Textarea
              id="ad-transition-note"
              autoFocus
              value={noteValue}
              onChange={(event) => setNoteValue(event.target.value)}
            />
          </Field>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setNotePrompt(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              variant={notePrompt === "cancelled" ? "destructive" : "primary"}
              disabled={!noteValue.trim() || transitioning !== null}
              onClick={() => notePrompt && void runTransition(notePrompt, noteValue.trim())}
            >
              {transitioning ? "Working…" : "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={(next) => (next ? undefined : setDeleteOpen(false))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this activity?</DialogTitle>
            <DialogDescription>
              It can be restored from Deleted records. This does not undo any decision it was
              part of.
            </DialogDescription>
          </DialogHeader>
          {deleteError ? <Alert variant="error">{deleteError}</Alert> : null}
          <Field label="Reason" htmlFor="ad-delete-reason" required>
            <Textarea
              id="ad-delete-reason"
              autoFocus
              value={deleteReason}
              onChange={(event) => setDeleteReason(event.target.value)}
            />
          </Field>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={!deleteReason.trim() || deleting}
              onClick={() => void submitDelete()}
            >
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sheet>
  );
}
