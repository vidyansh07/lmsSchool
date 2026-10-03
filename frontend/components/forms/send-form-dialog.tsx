"use client";

/**
 * "Send to someone": pick a person, optionally a due date and a note, and
 * send them a published form to fill (`POST /forms/assignments/`). The
 * person is found through the account search the caller may already use
 * (`GET /users/?search=`), which is scoped to the caller's own centre.
 */

import { useEffect, useId, useState } from "react";

import { Alert } from "@/components/ui/alert";
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
import { Input, Textarea } from "@/components/ui/input";
import { errorMessage, fieldErrors } from "@/lib/api";
import { sendForm } from "@/lib/forms";
import { ROLE_LABEL } from "@/lib/labels";
import { listUsers } from "@/lib/people";
import { cn } from "@/lib/utils";
import type { AdminUser, FormAssignmentDetail } from "@/types/api";

export function SendFormDialog({
  form,
  enquiryId,
  open,
  onClose,
  onSent,
}: {
  form: { slug: string; name: string };
  /** Send it about this enquiry: its answers then update the enquiry. */
  enquiryId?: string;
  open: boolean;
  onClose: () => void;
  onSent: (assignment: FormAssignmentDetail) => void;
}) {
  const uid = useId();
  const [search, setSearch] = useState("");
  const [people, setPeople] = useState<AdminUser[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [person, setPerson] = useState<AdminUser | null>(null);
  const [dueOn, setDueOn] = useState("");
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    const query = search.trim();
    if (query.length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setSearching(true);
      setSearchError(null);
      listUsers({ search: query, page_size: 8 }, controller.signal)
        .then((page) => setPeople(page.results))
        .catch((cause) => {
          if (!controller.signal.aborted) setSearchError(errorMessage(cause));
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [open, search]);

  function reset() {
    setSearch("");
    setPeople([]);
    setPerson(null);
    setDueOn("");
    setTitle("");
    setMessage("");
    setErrors({});
    setSearchError(null);
  }

  async function submit() {
    if (!person) {
      setErrors({ assigned_to: "Choose who should fill in the form." });
      return;
    }
    setSaving(true);
    setErrors({});
    try {
      const sent = await sendForm({
        form: form.slug,
        assigned_to: person.id,
        enquiry: enquiryId ?? null,
        // The end of the chosen day, local time.
        due_at: dueOn ? new Date(`${dueOn}T23:59:00`).toISOString() : null,
        title: title.trim(),
        message: message.trim(),
      });
      reset();
      onSent(sent);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  const showResults = search.trim().length >= 2;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send “{form.name}”</DialogTitle>
          <DialogDescription>
            They get a notification and find it under Forms. Their answers come
            back to you, and can start an automation rule.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

          <Field
            label="Who fills it in"
            htmlFor={`${uid}-search`}
            error={errors.assigned_to}
            hint="Search by name or email."
            required
          >
            <Input
              id={`${uid}-search`}
              value={person ? `${person.first_name} ${person.last_name}`.trim() || person.email : search}
              onChange={(event) => {
                setPerson(null);
                setSearch(event.target.value);
              }}
              autoComplete="off"
            />
          </Field>

          {!person && showResults ? (
            <div className="rounded-control border border-line" role="listbox" aria-label="People">
              {searching ? (
                <p className="px-3 py-2 text-sm text-ink-muted">Searching…</p>
              ) : searchError ? (
                <p className="px-3 py-2 text-sm text-danger">{searchError}</p>
              ) : people.length === 0 ? (
                <p className="px-3 py-2 text-sm text-ink-muted">No one matches.</p>
              ) : (
                people.map((candidate) => (
                  <button
                    key={candidate.id}
                    type="button"
                    role="option"
                    aria-selected={false}
                    className={cn(
                      "flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm",
                      "hover:bg-sunken focus-visible:bg-sunken focus-visible:outline-none",
                    )}
                    onClick={() => setPerson(candidate)}
                  >
                    <span>
                      <span className="font-medium text-ink">
                        {`${candidate.first_name} ${candidate.last_name}`.trim() || candidate.email}
                      </span>
                      <span className="block text-2xs text-ink-faint">{candidate.email}</span>
                    </span>
                    <span className="text-2xs text-ink-muted">
                      {ROLE_LABEL[candidate.role as keyof typeof ROLE_LABEL] ?? candidate.role}
                    </span>
                  </button>
                ))
              )}
            </div>
          ) : null}

          <Field label="Due by" htmlFor={`${uid}-due`} error={errors.due_at} hint="Optional.">
            <Input
              id={`${uid}-due`}
              type="date"
              value={dueOn}
              onChange={(event) => setDueOn(event.target.value)}
            />
          </Field>
          <Field label="Title" htmlFor={`${uid}-title`} error={errors.title} hint={`Defaults to “${form.name}”.`}>
            <Input id={`${uid}-title`} value={title} onChange={(event) => setTitle(event.target.value)} />
          </Field>
          <Field label="Message" htmlFor={`${uid}-message`} error={errors.message}>
            <Textarea
              id={`${uid}-message`}
              rows={3}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
            />
          </Field>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              reset();
              onClose();
            }}
          >
            Cancel
          </Button>
          <Button type="button" disabled={saving} onClick={() => void submit()}>
            {saving ? "Sending…" : "Send form"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
