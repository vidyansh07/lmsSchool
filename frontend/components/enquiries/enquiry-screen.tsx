"use client";

/**
 * One enquiry (`/enquiries/[id]`): who asked and about what, where it stands
 * in the pipeline, and everything done about it — its activities (calls,
 * demo classes), the forms sent about it, and its history. A counsellor
 * moves it along here, logs a call, or sends a follow-up form; automation
 * rules on "Enquiry stage changed" pick up from whatever they change.
 */

import Link from "next/link";
import { useId, useState } from "react";
import { ArrowLeft, Plus, Send } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { FormAssignmentsTable } from "@/components/forms/form-assignments-table";
import { SendFormDialog } from "@/components/forms/send-form-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ActivityDrawer } from "@/components/work/activity-drawer";
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
import { PageHeader } from "@/components/ui/layout";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { errorMessage, fieldErrors } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import { updateEnquiry, type EnquiryChanges } from "@/lib/enquiries";
import { formatDateTime } from "@/lib/format";
import {
  ACTIVITY_STATUS_LABEL,
  ACTIVITY_STATUS_VARIANT,
  ENQUIRY_STAGE_LABEL,
  ENQUIRY_STAGE_VARIANT,
  ENQUIRY_STAGES,
} from "@/lib/labels";
import { createActivity, type ActivityTypeListResponse } from "@/lib/work";
import type {
  Activity,
  EnquiryDetail,
  EnquiryStage,
  FormAssignment,
  Paginated,
} from "@/types/api";

const LOST_STAGES: EnquiryStage[] = ["not_interested", "not_eligible"];

/** `<input type="datetime-local">` value for an ISO instant, in local time. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function Facts({ enquiry }: { enquiry: EnquiryDetail }) {
  const facts: [string, string][] = [
    ["Mobile", enquiry.mobile],
    ["WhatsApp", enquiry.whatsapp_number || "Same as mobile"],
    ["Email", enquiry.email || "—"],
    ["City", [enquiry.city, enquiry.state].filter(Boolean).join(", ") || "—"],
    ["Course", [enquiry.course, enquiry.track].filter(Boolean).join(" · ") || "—"],
    ["Centre", enquiry.preferred_centre || "—"],
    ["Mode", enquiry.mode || "—"],
    ["Batch timing", enquiry.batch_timing || "—"],
    ["Qualification", enquiry.qualification || "—"],
    ["Source", enquiry.source || "—"],
    ["Campaign", [enquiry.utm_source, enquiry.utm_campaign].filter(Boolean).join(" / ") || "—"],
    ["Lead quality", enquiry.lead_quality ? `${enquiry.lead_quality} of 5` : "—"],
    ["Owner", enquiry.owner?.name ?? "Unassigned"],
    ["Entered by", enquiry.created_by?.name ?? "—"],
    ["Last contacted", enquiry.last_contacted_at ? formatDateTime(enquiry.last_contacted_at) : "—"],
    ["Created", formatDateTime(enquiry.created_at)],
  ];
  return (
    <Card>
      <CardContent className="space-y-4 pt-5">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          {facts.map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-2xs font-medium uppercase tracking-wide text-ink-faint">{label}</dt>
              <dd className="truncate text-sm text-ink">{value}</dd>
            </div>
          ))}
        </dl>
        {enquiry.remarks ? (
          <p className="whitespace-pre-line border-t border-line pt-3 text-sm text-ink-muted">
            {enquiry.remarks}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function PipelineCard({
  enquiry,
  onSaved,
}: {
  enquiry: EnquiryDetail;
  onSaved: (message: string) => void;
}) {
  const uid = useId();
  const { user } = useAuth();
  const [stage, setStage] = useState<EnquiryStage>(enquiry.stage);
  const [lostReason, setLostReason] = useState(enquiry.lost_reason);
  const [followUp, setFollowUp] = useState(toLocalInput(enquiry.next_follow_up_at));
  const [quality, setQuality] = useState(enquiry.lead_quality ? String(enquiry.lead_quality) : "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  async function save(extra: EnquiryChanges = {}) {
    setSaving(true);
    setErrors({});
    try {
      await updateEnquiry(enquiry.id, {
        stage,
        lost_reason: LOST_STAGES.includes(stage) ? lostReason : "",
        next_follow_up_at: followUp ? new Date(followUp).toISOString() : null,
        lead_quality: quality ? Number(quality) : null,
        ...extra,
      });
      onSaved(extra.owner ? "The enquiry is yours now." : "Saved.");
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Pipeline</CardTitle>
        {enquiry.can_manage && user && enquiry.owner?.id !== user.id ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={saving}
            onClick={() => void save({ owner: user.id })}
          >
            Assign to me
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="Stage" htmlFor={`${uid}-stage`} error={errors.stage}>
            <Select
              id={`${uid}-stage`}
              disabled={!enquiry.can_manage}
              value={stage}
              onChange={(event) => setStage(event.target.value as EnquiryStage)}
            >
              {ENQUIRY_STAGES.map((value) => (
                <option key={value} value={value}>
                  {ENQUIRY_STAGE_LABEL[value]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Next follow-up" htmlFor={`${uid}-follow-up`} error={errors.next_follow_up_at}>
            <Input
              id={`${uid}-follow-up`}
              type="datetime-local"
              disabled={!enquiry.can_manage}
              value={followUp}
              onChange={(event) => setFollowUp(event.target.value)}
            />
          </Field>
          <Field label="Lead quality" htmlFor={`${uid}-quality`} error={errors.lead_quality}>
            <Select
              id={`${uid}-quality`}
              disabled={!enquiry.can_manage}
              value={quality}
              onChange={(event) => setQuality(event.target.value)}
            >
              <option value="">Not rated</option>
              {[1, 2, 3, 4, 5].map((score) => (
                <option key={score} value={score}>
                  {score} of 5
                </option>
              ))}
            </Select>
          </Field>
          {LOST_STAGES.includes(stage) ? (
            <Field
              label="Lost reason"
              htmlFor={`${uid}-lost`}
              error={errors.lost_reason}
              className="sm:col-span-3"
            >
              <Input
                id={`${uid}-lost`}
                disabled={!enquiry.can_manage}
                value={lostReason}
                onChange={(event) => setLostReason(event.target.value)}
              />
            </Field>
          ) : null}
        </div>
        {enquiry.can_manage ? (
          <div className="flex justify-end">
            <Button type="button" disabled={saving} onClick={() => void save()}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        ) : (
          <p className="text-2xs text-ink-faint">Only its owner or a manager at its centre can change it.</p>
        )}
      </CardContent>
    </Card>
  );
}

function LogActivityDialog({
  enquiry,
  open,
  onClose,
  onLogged,
}: {
  enquiry: EnquiryDetail;
  open: boolean;
  onClose: () => void;
  onLogged: () => void;
}) {
  const uid = useId();
  const { user } = useAuth();
  const { data } = useApi<ActivityTypeListResponse>("/api/v1/activity-types/");
  const types = (data?.results ?? []).filter(
    (type) => type.subject === "enquiry" && type.status === "active",
  );
  const [type, setType] = useState("");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const chosen = type || types[0]?.slug || "";

  async function submit() {
    if (!chosen) return;
    setSaving(true);
    setErrors({});
    try {
      await createActivity({
        enquiry: enquiry.id,
        activity_type: chosen,
        title: title.trim() || undefined,
        summary: summary.trim(),
        assigned_to: user?.id,
        due_at: dueAt ? new Date(dueAt).toISOString() : undefined,
      });
      setTitle("");
      setSummary("");
      setDueAt("");
      onLogged();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New activity for {enquiry.full_name}</DialogTitle>
          <DialogDescription>
            Assigned to you. Completing a counselling call with its form moves the enquiry&rsquo;s stage.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
          <Field label="Activity" htmlFor={`${uid}-type`} error={errors.activity_type}>
            <Select id={`${uid}-type`} value={chosen} onChange={(event) => setType(event.target.value)}>
              {types.map((option) => (
                <option key={option.slug} value={option.slug}>
                  {option.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Title" htmlFor={`${uid}-title`} hint="Defaults to the activity's name.">
            <Input id={`${uid}-title`} value={title} onChange={(event) => setTitle(event.target.value)} />
          </Field>
          <Field label="Notes" htmlFor={`${uid}-summary`} error={errors.summary}>
            <Textarea
              id={`${uid}-summary`}
              rows={3}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
            />
          </Field>
          <Field label="Due" htmlFor={`${uid}-due`} error={errors.due_at}>
            <Input
              id={`${uid}-due`}
              type="datetime-local"
              value={dueAt}
              onChange={(event) => setDueAt(event.target.value)}
            />
          </Field>
        </div>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" disabled={saving || !chosen} onClick={() => void submit()}>
            {saving ? "Creating…" : "Create activity"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ActivitiesCard({ enquiry }: { enquiry: EnquiryDetail }) {
  const { data, error, isLoading, reload } = useApi<Paginated<Activity>>(
    `/api/v1/activities/?enquiry=${enquiry.id}&ordering=-created_at`,
  );
  const [logging, setLogging] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const rows = data?.results ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Activities</CardTitle>
        <Button type="button" variant="outline" size="sm" onClick={() => setLogging(true)}>
          <Plus className="size-4" aria-hidden="true" />
          New activity
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingState label="Loading activities…" rows={2} />
        ) : error ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No activities yet"
            description="Log a counselling call or book a demo class. Automation rules can create them too."
          />
        ) : (
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Activity</Th>
                  <Th>Assigned to</Th>
                  <Th>Due</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="hover:bg-sunken/40">
                    <Td>
                      <button
                        type="button"
                        className="text-left font-medium text-ink underline-offset-2 hover:underline"
                        onClick={() => setOpenId(row.id)}
                      >
                        {row.title}
                      </button>
                      <span className="block text-2xs text-ink-faint">{row.type.name}</span>
                    </Td>
                    <Td>{row.assigned_to?.name ?? "—"}</Td>
                    <Td className="whitespace-nowrap tabular-nums">
                      {row.due_at ? formatDateTime(row.due_at) : "—"}
                    </Td>
                    <Td>
                      <Badge variant={ACTIVITY_STATUS_VARIANT[row.status]}>
                        {ACTIVITY_STATUS_LABEL[row.status]}
                      </Badge>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
        )}
      </CardContent>
      <LogActivityDialog
        enquiry={enquiry}
        open={logging}
        onClose={() => setLogging(false)}
        onLogged={() => {
          setLogging(false);
          reload();
        }}
      />
      <ActivityDrawer
        activityId={openId}
        onOpenChange={(open) => (open ? undefined : setOpenId(null))}
        onChanged={reload}
      />
    </Card>
  );
}

function FormsCard({ enquiry, maySend }: { enquiry: EnquiryDetail; maySend: boolean }) {
  const { data, error, isLoading, reload } = useApi<Paginated<FormAssignment>>(
    `/api/v1/forms/assignments/?box=all&enquiry=${enquiry.id}`,
  );
  const [sending, setSending] = useState(false);
  const rows = data?.results ?? [];
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Forms</CardTitle>
        {maySend ? (
          <Button type="button" variant="outline" size="sm" onClick={() => setSending(true)}>
            <Send className="size-4" aria-hidden="true" />
            Send follow-up form
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingState label="Loading forms…" rows={2} />
        ) : error ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : rows.length === 0 ? (
          <p className="text-sm text-ink-muted">No forms about this enquiry yet.</p>
        ) : (
          <FormAssignmentsTable rows={rows} showAssignee />
        )}
      </CardContent>
      {maySend ? (
        <SendFormDialog
          form={{ slug: "enquiry-follow-up", name: "Enquiry follow-up" }}
          enquiryId={enquiry.id}
          open={sending}
          onClose={() => setSending(false)}
          onSent={() => {
            setSending(false);
            reload();
          }}
        />
      ) : null}
    </Card>
  );
}

const HISTORY_LABEL: Record<string, string> = {
  "enquiry.created": "Enquiry created",
  "enquiry.updated": "Enquiry updated",
};

function HistoryCard({ enquiry }: { enquiry: EnquiryDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">History</CardTitle>
      </CardHeader>
      <CardContent>
        {enquiry.history.length === 0 ? (
          <p className="text-sm text-ink-muted">Nothing recorded yet.</p>
        ) : (
          <ol className="space-y-3">
            {enquiry.history.map((row) => {
              const changed = Array.isArray(row.context.changed)
                ? (row.context.changed as string[])
                : [];
              const stage = typeof row.context.stage === "string" ? row.context.stage : null;
              return (
                <li key={row.id} className="flex gap-3 text-sm">
                  <span className="w-36 shrink-0 tabular-nums text-ink-faint">
                    {formatDateTime(row.created_at)}
                  </span>
                  <span className="min-w-0 text-ink">
                    {HISTORY_LABEL[row.action] ?? row.action}
                    {stage ? ` — stage now ${ENQUIRY_STAGE_LABEL[stage as EnquiryStage] ?? stage}` : ""}
                    {!stage && changed.length > 0 ? ` — ${changed.join(", ")}` : ""}
                    {row.context.repeat ? " (repeat enquiry)" : ""}
                    <span className="block text-2xs text-ink-faint">{row.actor}</span>
                  </span>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

export function EnquiryScreen({ id }: { id: string }) {
  const { user } = useAuth();
  const maySend = can(user?.capabilities, Capability.formAssign);
  const { data, error, isLoading, reload } = useApi<EnquiryDetail>(`/api/v1/enquiries/${id}/`);
  const [notice, setNotice] = useState<string | null>(null);

  if (isLoading) return <LoadingState label="Loading enquiry…" rows={6} />;
  if (error || !data) {
    return (
      <ErrorState
        title="Could not load this enquiry"
        message={error ? errorMessage(error) : "It may have been removed, or it is at another centre."}
        requestId={error?.requestId || undefined}
        onRetry={reload}
      />
    );
  }

  return (
    <div className="space-y-6">
      <Link
        href="/enquiries"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Enquiries
      </Link>
      <PageHeader
        title={data.full_name}
        meta={[data.course, data.source].filter(Boolean).join(" · ") || "Enquiry"}
      >
        <Badge variant={ENQUIRY_STAGE_VARIANT[data.stage]}>{ENQUIRY_STAGE_LABEL[data.stage]}</Badge>
      </PageHeader>
      {notice ? <Alert variant="success">{notice}</Alert> : null}

      <Facts enquiry={data} />
      <PipelineCard
        key={data.updated_at}
        enquiry={data}
        onSaved={(message) => {
          setNotice(message);
          reload();
        }}
      />
      <ActivitiesCard enquiry={data} />
      <FormsCard enquiry={data} maySend={maySend} />
      <HistoryCard enquiry={data} />
    </div>
  );
}
