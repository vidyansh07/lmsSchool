"use client";

/**
 * One form sent to someone (`/forms/[id]`): the person it was sent to fills
 * it in here; the sender and the staff who read submissions see the answers
 * once it is in. Notifications about a sent or submitted form link to it.
 */

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft } from "lucide-react";

import { Confirm } from "@/components/confirm";
import { FieldRenderer, valuesForSubmit, type FormValues } from "@/components/forms/field-renderer";
import { assignmentSender } from "@/components/forms/form-assignments-table";
import { ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/layout";
import { useApi } from "@/hooks/use-api";
import { errorMessage, fieldErrors } from "@/lib/api";
import { cancelFormAssignment, submitFormAssignment } from "@/lib/forms";
import { formatDateTime } from "@/lib/format";
import {
  FORM_ASSIGNMENT_STATUS_LABEL,
  FORM_ASSIGNMENT_STATUS_VARIANT,
} from "@/lib/labels";
import type { FormAssignmentDetail } from "@/types/api";

export function FormAssignmentScreen({ id }: { id: string }) {
  const { data, error, isLoading, reload } = useApi<FormAssignmentDetail>(
    `/api/v1/forms/assignments/${id}/`,
  );
  const [values, setValues] = useState<FormValues>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  if (isLoading) return <LoadingState label="Loading form…" rows={6} />;
  if (error || !data) {
    return (
      <ErrorState
        title="Could not load this form"
        message={error?.message ?? "It may have been removed, or it was not sent to you."}
        requestId={error?.requestId || undefined}
        onRetry={reload}
      />
    );
  }

  async function submit(assignment: FormAssignmentDetail) {
    setSubmitting(true);
    setErrors({});
    setFailure(null);
    try {
      await submitFormAssignment(assignment.id, valuesForSubmit(assignment.fields, values));
      setNotice("Submitted. Thank you.");
      reload();
    } catch (cause) {
      const { __all__, ...rest } = fieldErrors(cause);
      setErrors(rest);
      setFailure(
        __all__ ??
          (Object.keys(rest).length > 0 ? "Some answers need attention." : errorMessage(cause)),
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel(assignment: FormAssignmentDetail) {
    setCancelling(true);
    setFailure(null);
    try {
      await cancelFormAssignment(assignment.id);
      setConfirmingCancel(false);
      setNotice("The form request was cancelled.");
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause));
    } finally {
      setCancelling(false);
    }
  }

  const facts = [
    { label: "From", value: assignmentSender(data) },
    { label: "Filled in by", value: data.assigned_to.name },
    { label: "About", value: data.student?.name ?? "—" },
    { label: "Due", value: data.due_at ? formatDateTime(data.due_at) : "No due date" },
    {
      label: data.status === "cancelled" ? "Cancelled" : "Submitted",
      value: data.submitted_at
        ? formatDateTime(data.submitted_at)
        : data.cancelled_at
          ? formatDateTime(data.cancelled_at)
          : "Not yet",
    },
  ];

  return (
    <div className="space-y-6">
      <Link
        href="/forms"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Forms
      </Link>

      <PageHeader title={data.title || data.form.name} meta={data.form.name}>
        <Badge variant={FORM_ASSIGNMENT_STATUS_VARIANT[data.status]}>
          {FORM_ASSIGNMENT_STATUS_LABEL[data.status]}
        </Badge>
        {data.is_overdue ? <Badge variant="error">Overdue</Badge> : null}
        {data.can_cancel ? (
          <Button type="button" variant="outline" onClick={() => setConfirmingCancel(true)}>
            Cancel request
          </Button>
        ) : null}
      </PageHeader>

      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {failure ? <Alert variant="error">{failure}</Alert> : null}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-5">
        {facts.map((fact) => (
          <div key={fact.label} className="min-w-0">
            <dt className="text-2xs font-medium uppercase tracking-wide text-ink-faint">
              {fact.label}
            </dt>
            <dd className="truncate text-sm text-ink">{fact.value}</dd>
          </div>
        ))}
      </dl>

      {data.message ? (
        <Card>
          <CardContent className="pt-5">
            <p className="whitespace-pre-line text-sm text-ink">{data.message}</p>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {data.can_submit ? "Your answers" : "Answers"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {data.can_submit ? (
            <form
              className="space-y-5"
              onSubmit={(event) => {
                event.preventDefault();
                void submit(data);
              }}
            >
              <FieldRenderer
                fields={data.fields}
                values={values}
                errors={errors}
                onChange={(key, value) => setValues((current) => ({ ...current, [key]: value }))}
              />
              <div className="flex justify-end">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Submitting…" : "Submit"}
                </Button>
              </div>
            </form>
          ) : data.status === "submitted" && data.values ? (
            <FieldRenderer fields={data.fields} values={data.values} readOnly />
          ) : data.status === "cancelled" ? (
            <p className="text-sm text-ink-muted">This request was cancelled before it was filled in.</p>
          ) : (
            <p className="text-sm text-ink-muted">
              Waiting for {data.assigned_to.name} to fill this in.
            </p>
          )}
        </CardContent>
      </Card>

      <Confirm
        open={confirmingCancel}
        title="Cancel this form request?"
        description={`${data.assigned_to.name} will no longer be able to fill it in.`}
        confirmLabel="Cancel request"
        cancelLabel="Keep it"
        isConfirming={cancelling}
        onConfirm={() => void cancel(data)}
        onCancel={() => setConfirmingCancel(false)}
      />
    </div>
  );
}

