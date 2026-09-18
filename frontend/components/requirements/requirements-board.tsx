"use client";

/**
 * Trainer requirements (D-132): a manager asks the teaching staff for
 * something — "who can cover Linux next week?" — every trainer at the centre
 * is told, they answer on it here, and the manager closes it naming who took
 * it. One board for both sides: the manager sees the raise and close
 * controls, a trainer sees the reply box, and everybody sees the same record.
 *
 * `?open=<id>` in the address bar (the link in a notification) expands that
 * requirement on arrival.
 */

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { MessageSquareReply, Plus } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Pagination } from "@/components/pagination";
import { useList } from "@/hooks/use-list";
import { errorMessage, fieldErrors } from "@/lib/api";
import { listBatches } from "@/lib/batches";
import { Capability, can } from "@/lib/capabilities";
import { fallback, formatDate, formatDateTime } from "@/lib/format";
import {
  REQUIREMENT_STATUS_LABEL,
  REQUIREMENT_STATUS_VARIANT,
} from "@/lib/labels";
import { listTrainers } from "@/lib/people";
import {
  closeRequirement,
  listRequirements,
  raiseRequirement,
  removeRequirement,
  replyToRequirement,
} from "@/lib/requirements";
import type {
  BatchListRow,
  RequirementStatus,
  TrainerListRow,
  TrainerRequirement,
} from "@/types/api";

const STATUS_FILTERS: { value: RequirementStatus | ""; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "fulfilled", label: "Fulfilled" },
  { value: "closed", label: "Closed without a taker" },
  { value: "", label: "Everything" },
];

export function RequirementsBoard() {
  const { user } = useAuth();
  const canManage = can(user?.capabilities, Capability.requirementManage);
  const searchParams = useSearchParams();
  const openParam = searchParams.get("open") ?? "";

  const list = useList<TrainerRequirement>(listRequirements, {
    page_size: 20,
    status: openParam ? "" : "open",
  });
  const [expanded, setExpanded] = useState<string>(openParam);
  const [isRaising, setIsRaising] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const rows = list.data?.results ?? [];

  return (
    <div className="animate-rise-in space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            Trainer requirements
          </h1>
          <p className="text-sm text-muted-foreground">
            {canManage
              ? "Ask the trainers of your centre for something. Every trainer is told, they answer here, and you close it naming who took it."
              : "What your centre needs from its trainers. Answer on one if you can take it."}
          </p>
        </div>
        {canManage ? (
          <Button type="button" onClick={() => setIsRaising(true)}>
            <Plus className="size-4" aria-hidden="true" />
            Raise a requirement
          </Button>
        ) : null}
      </div>

      {notice ? <Alert variant="success">{notice}</Alert> : null}

      <div className="flex flex-wrap items-end gap-3">
        <Field label="Show" htmlFor="requirement-status" className="min-w-56">
          <Select
            id="requirement-status"
            value={String(list.query.status ?? "")}
            onChange={(event) =>
              list.setQuery({ status: event.target.value, page: 1 })
            }
          >
            {STATUS_FILTERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Search" htmlFor="requirement-search" className="min-w-64">
          <Input
            id="requirement-search"
            placeholder="Title, details or batch code"
            value={String(list.query.search ?? "")}
            onChange={(event) =>
              list.setQuery({ search: event.target.value, page: 1 })
            }
          />
        </Field>
      </div>

      {list.isLoading ? (
        <LoadingState label="Loading requirements…" rows={3} />
      ) : list.error ? (
        <ErrorState
          title="Could not load the requirements"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing here"
          description={
            canManage
              ? "No requirement matches. Raise one when the centre needs something from its trainers."
              : "Nothing is being asked of the trainers right now."
          }
        />
      ) : (
        <div className="space-y-3">
          {rows.map((row) => (
            <RequirementCard
              key={row.id}
              row={row}
              canManage={canManage}
              currentUserId={user?.id}
              isExpanded={expanded === row.id}
              onToggle={() =>
                setExpanded((current) => (current === row.id ? "" : row.id))
              }
              onChanged={(message) => {
                setNotice(message);
                list.reload();
              }}
            />
          ))}
        </div>
      )}

      {list.data ? (
        <Pagination
          page={list.data.page}
          totalPages={list.data.total_pages}
          count={list.data.count}
          pageSize={list.data.page_size}
          onPageChange={(page) => list.setQuery({ page })}
        />
      ) : null}

      {isRaising ? (
        <RaiseDialog
          onClose={() => setIsRaising(false)}
          onRaised={(row) => {
            setIsRaising(false);
            setNotice(
              `Raised "${row.title}". The trainers of your centre have been told.`,
            );
            setExpanded(row.id);
            list.setQuery({ status: "open", page: 1 });
          }}
        />
      ) : null}
    </div>
  );
}

function RequirementCard({
  row,
  canManage,
  currentUserId,
  isExpanded,
  onToggle,
  onChanged,
}: {
  row: TrainerRequirement;
  canManage: boolean;
  currentUserId: string | undefined;
  isExpanded: boolean;
  onToggle: () => void;
  onChanged: (message: string) => void;
}) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isClosing, setIsClosing] = useState(false);
  const [removeReason, setRemoveReason] = useState("");
  const [isRemoving, setIsRemoving] = useState(false);
  const isOpen = row.status === "open";

  async function run(
    key: string,
    action: () => Promise<unknown>,
    message: string,
  ) {
    setBusy(key);
    setError(null);
    try {
      await action();
      onChanged(message);
    } catch (cause) {
      setError(errorMessage(cause, "That could not be done."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card
      data-testid="requirement"
      className={isOpen ? undefined : "opacity-90"}
    >
      <CardHeader className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={isExpanded}
            className="press text-left hover:text-primary"
          >
            <CardTitle className="text-base">{row.title}</CardTitle>
          </button>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={REQUIREMENT_STATUS_VARIANT[row.status]}>
              {REQUIREMENT_STATUS_LABEL[row.status]}
            </Badge>
            {row.batch_code ? (
              <Badge variant="blue">{row.batch_code}</Badge>
            ) : null}
            {row.needed_by ? (
              <Badge variant="amber">
                Needed by {formatDate(row.needed_by)}
              </Badge>
            ) : null}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Raised by {fallback(row.raised_by_name)} on{" "}
          {formatDateTime(row.created_at)} ·{" "}
          {row.reply_count === 1 ? "1 reply" : `${row.reply_count} replies`}
          {row.status === "fulfilled" && row.fulfilled_by_name
            ? ` · fulfilled by ${row.fulfilled_by_name}`
            : null}
          {row.status === "closed" ? " · closed without a taker" : null}
        </p>
      </CardHeader>

      {isExpanded ? (
        <CardContent className="animate-rise-in space-y-4">
          {row.details ? (
            <p className="whitespace-pre-line text-sm">{row.details}</p>
          ) : (
            <p className="text-sm text-muted-foreground">No further details.</p>
          )}
          {row.batch_name ? (
            <p className="text-sm text-muted-foreground">
              About the batch {row.batch_name}.
            </p>
          ) : null}

          {row.replies.length > 0 ? (
            <ol className="space-y-2" aria-label="Replies">
              {row.replies.map((reply) => (
                <li
                  key={reply.id}
                  className="rounded-md border border-border bg-muted/40 p-3 text-sm"
                >
                  <p className="text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">
                      {reply.author_name}
                    </span>
                    {reply.author === currentUserId ? " (you)" : null} ·{" "}
                    {formatDateTime(reply.created_at)}
                  </p>
                  <p className="mt-1 whitespace-pre-line">{reply.message}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">
              Nobody has answered yet.
            </p>
          )}

          {row.closing_note ? (
            <Alert variant="info">
              {row.closed_by_name ? `${row.closed_by_name}: ` : null}
              {row.closing_note}
            </Alert>
          ) : null}

          {error ? <Alert variant="error">{error}</Alert> : null}

          {isOpen ? (
            <form
              className="space-y-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (!message.trim()) return;
                void run(
                  "reply",
                  async () => {
                    await replyToRequirement(row.id, message.trim());
                    setMessage("");
                  },
                  "Your reply has been posted.",
                );
              }}
            >
              <Field label="Reply" htmlFor={`reply-${row.id}`}>
                <Textarea
                  id={`reply-${row.id}`}
                  rows={2}
                  maxLength={2000}
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder={
                    canManage ? "Add to the ask…" : "I can take it from…"
                  }
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="submit"
                  size="sm"
                  disabled={busy !== null || !message.trim()}
                >
                  <MessageSquareReply className="size-4" aria-hidden="true" />
                  {busy === "reply" ? "Posting…" : "Post reply"}
                </Button>
                {canManage ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setIsClosing(true)}
                  >
                    Close this requirement
                  </Button>
                ) : null}
                {canManage ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setIsRemoving(true)}
                  >
                    Remove
                  </Button>
                ) : null}
              </div>
            </form>
          ) : null}

          {isRemoving ? (
            <form
              className="flex flex-wrap items-end gap-2 rounded-md border border-border p-3"
              onSubmit={(event) => {
                event.preventDefault();
                void run(
                  "remove",
                  () => removeRequirement(row.id, removeReason.trim()),
                  "The requirement has been removed. It can be restored from the recycle bin.",
                );
              }}
            >
              <Field
                label="Why remove it?"
                htmlFor={`remove-${row.id}`}
                className="min-w-64 flex-1"
              >
                <Input
                  id={`remove-${row.id}`}
                  required
                  maxLength={255}
                  value={removeReason}
                  onChange={(event) => setRemoveReason(event.target.value)}
                />
              </Field>
              <Button
                type="submit"
                size="sm"
                variant="destructive"
                disabled={busy !== null || !removeReason.trim()}
              >
                {busy === "remove" ? "Removing…" : "Remove"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setIsRemoving(false)}
              >
                Keep it
              </Button>
            </form>
          ) : null}
        </CardContent>
      ) : null}

      {isClosing ? (
        <CloseDialog
          row={row}
          onClose={() => setIsClosing(false)}
          onClosed={(message) => {
            setIsClosing(false);
            onChanged(message);
          }}
        />
      ) : null}
    </Card>
  );
}

/** Mounted fresh on every open, so its state starts empty without an effect. */
function RaiseDialog({
  onClose,
  onRaised,
}: {
  onClose: () => void;
  onRaised: (row: TrainerRequirement) => void;
}) {
  const [form, setForm] = useState({
    title: "",
    details: "",
    batch: "",
    needed_by: "",
  });
  const [batches, setBatches] = useState<BatchListRow[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listBatches({ page_size: 100 })
      .then((page) => {
        if (!cancelled) setBatches(page.results);
      })
      .catch(() => {
        // The batch is optional; a failed lookup only shortens the list.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    setFormError(null);
    try {
      const row = await raiseRequirement({
        title: form.title.trim(),
        details: form.details.trim(),
        batch: form.batch || null,
        needed_by: form.needed_by || null,
      });
      onRaised(row);
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      if (Object.keys(fields).length === 0)
        setFormError(errorMessage(cause, "That could not be raised."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Raise a requirement</DialogTitle>
            <DialogDescription>
              Every trainer at your centre is told straight away and can answer
              on it.
            </DialogDescription>
          </DialogHeader>

          {formError ? <Alert variant="error">{formError}</Alert> : null}

          <Field
            label="What is needed"
            htmlFor="requirement-title"
            error={errors.title}
          >
            <Input
              id="requirement-title"
              required
              maxLength={160}
              value={form.title}
              onChange={(event) =>
                setForm({ ...form, title: event.target.value })
              }
              placeholder="A trainer for the evening Python batch"
            />
          </Field>
          <Field
            label="Details"
            htmlFor="requirement-details"
            error={errors.details}
          >
            <Textarea
              id="requirement-details"
              rows={3}
              maxLength={4000}
              value={form.details}
              onChange={(event) =>
                setForm({ ...form, details: event.target.value })
              }
            />
          </Field>
          <Field
            label="Batch (optional)"
            htmlFor="requirement-batch"
            error={errors.batch}
          >
            <Select
              id="requirement-batch"
              value={form.batch}
              onChange={(event) =>
                setForm({ ...form, batch: event.target.value })
              }
            >
              <option value="">Not about one batch</option>
              {batches.map((batch) => (
                <option key={batch.id} value={batch.id}>
                  {batch.code} · {batch.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Needed by (optional)"
            htmlFor="requirement-needed-by"
            error={errors.needed_by}
          >
            <Input
              id="requirement-needed-by"
              type="date"
              value={form.needed_by}
              onChange={(event) =>
                setForm({ ...form, needed_by: event.target.value })
              }
            />
          </Field>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving || !form.title.trim()}>
              {isSaving ? "Raising…" : "Raise and tell the trainers"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CloseDialog({
  row,
  onClose,
  onClosed,
}: {
  row: TrainerRequirement;
  onClose: () => void;
  onClosed: (message: string) => void;
}) {
  const [trainers, setTrainers] = useState<TrainerListRow[]>([]);
  const [fulfilledBy, setFulfilledBy] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listTrainers({ page_size: 100 })
      .then((page) => {
        if (!cancelled) setTrainers(page.results);
      })
      .catch(() => {
        // Closing without naming anybody still works.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The people who answered come first: they are the likely takers.
  const answered = new Set(row.replies.map((reply) => reply.author));
  const ordered = [...trainers].sort(
    (a, b) => Number(answered.has(b.user_id)) - Number(answered.has(a.user_id)),
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setError(null);
    try {
      const closed = await closeRequirement(row.id, {
        fulfilled_by: fulfilledBy || null,
        note: note.trim(),
      });
      onClosed(
        closed.status === "fulfilled" && closed.fulfilled_by_name
          ? `Closed: fulfilled by ${closed.fulfilled_by_name}.`
          : "Closed without a taker.",
      );
    } catch (cause) {
      setError(errorMessage(cause, "That could not be closed."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Close “{row.title}”</DialogTitle>
            <DialogDescription>
              Name who took it, or close it without a taker. Everyone who
              answered is told.
            </DialogDescription>
          </DialogHeader>

          {error ? <Alert variant="error">{error}</Alert> : null}

          <Field label="Fulfilled by" htmlFor="requirement-fulfilled-by">
            <Select
              id="requirement-fulfilled-by"
              value={fulfilledBy}
              onChange={(event) => setFulfilledBy(event.target.value)}
            >
              <option value="">Nobody — close it</option>
              {ordered.map((trainer) => (
                <option key={trainer.id} value={trainer.id}>
                  {trainer.full_name}
                  {answered.has(trainer.user_id) ? " (answered)" : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Note (optional)" htmlFor="requirement-closing-note">
            <Input
              id="requirement-closing-note"
              maxLength={300}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Starts Monday."
            />
          </Field>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving
                ? "Closing…"
                : fulfilledBy
                  ? "Mark fulfilled"
                  : "Close it"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
