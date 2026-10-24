"use client";

/**
 * One enquiry (`/enquiries/[id]`): who asked and about what, where it stands
 * in the pipeline, and everything done about it — its activities (calls,
 * demo classes), the forms sent about it, and its history. A counsellor
 * moves it along here, logs a call, or sends a follow-up form; automation
 * rules on "Enquiry stage changed" pick up from whatever they change.
 */

import Link from "next/link";
import { useId, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  CalendarPlus,
  ExternalLink,
  Mail,
  MessageSquarePlus,
  Phone,
  Plus,
  Send,
  Shuffle,
  UserPlus,
} from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { FormAssignmentsTable } from "@/components/forms/form-assignments-table";
import { SendFormDialog } from "@/components/forms/send-form-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ActivityDrawer } from "@/components/work/activity-drawer";
import { AddEventDrawer } from "@/components/work/add-event-drawer";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/layout";
import { StageTrail, type StageTrailStep } from "@/components/ui/stage-trail";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { errorMessage, fieldErrors } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import {
  addEnquiryNote,
  registerLeadHref,
  updateEnquiry,
  type EnquiryChanges,
} from "@/lib/enquiries";
import { formatDateTime, formatTime } from "@/lib/format";
import {
  ACTIVITY_STATUS_LABEL,
  ACTIVITY_STATUS_VARIANT,
  ENQUIRY_STAGE_LABEL,
  ENQUIRY_STAGE_VARIANT,
  ENQUIRY_STAGES,
  LEAD_CHANNEL_LABEL,
} from "@/lib/labels";
import type {
  Activity,
  EnquiryDetail,
  EnquiryStage,
  EnquirySummary,
  FormAssignment,
  LeadChannel,
  Paginated,
} from "@/types/api";

/** The sources that mean "came in online" — mirrors `apps.enquiries.models.ONLINE_SOURCES`. */
const ONLINE_SOURCES = new Set(["website", "google", "facebook_instagram", "linkedin", "whatsapp"]);

const LOST_STAGES: EnquiryStage[] = ["not_interested", "not_eligible"];

/** `<input type="datetime-local">` value for an ISO instant, in local time. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

/** The three wrappers `PipelineCard` swaps in when it is already inside a
 *  dialog: a dialog supplies its own card, title and padding, and nesting a
 *  second `Card` inside one draws a box in a box. */
function PlainFrame({ children }: { children: ReactNode }) {
  return <div className="space-y-4">{children}</div>;
}
function PlainHead({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={className}>{children}</div>;
}
function PlainBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={className}>{children}</div>;
}

function PipelineCard({
  enquiry,
  sources,
  onSaved,
  plain = false,
}: {
  enquiry: EnquiryDetail;
  sources: { value: string; label: string }[];
  onSaved: (message: string) => void;
  /** Rendered inside the Change Stage dialog, which brings its own frame. */
  plain?: boolean;
}) {
  const uid = useId();
  const { user } = useAuth();
  const [stage, setStage] = useState<EnquiryStage>(enquiry.stage);
  const [lostReason, setLostReason] = useState(enquiry.lost_reason);
  const [followUp, setFollowUp] = useState(toLocalInput(enquiry.next_follow_up_at));
  const [quality, setQuality] = useState(enquiry.lead_quality ? String(enquiry.lead_quality) : "");
  const [source, setSource] = useState(enquiry.source);
  const [channel, setChannel] = useState<LeadChannel>(enquiry.channel);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const sourceOptions = sources.some((option) => option.value === source) || !source
    ? sources
    : [{ value: source, label: source }, ...sources];

  async function save(extra: EnquiryChanges = {}) {
    setSaving(true);
    setErrors({});
    try {
      await updateEnquiry(enquiry.id, {
        stage,
        lost_reason: LOST_STAGES.includes(stage) ? lostReason : "",
        next_follow_up_at: followUp ? new Date(followUp).toISOString() : null,
        lead_quality: quality ? Number(quality) : null,
        source,
        channel,
        ...extra,
      });
      onSaved(extra.owner ? "The enquiry is yours now." : "Saved.");
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  const Frame = plain ? PlainFrame : Card;
  const Head = plain ? PlainHead : CardHeader;
  const Body = plain ? PlainBody : CardContent;

  return (
    <Frame>
      <Head className="flex flex-row items-center justify-between space-y-0">
        {plain ? <span /> : <CardTitle className="text-base">Pipeline</CardTitle>}
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
      </Head>
      <Body className="space-y-4">
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
          <Field label="Source" htmlFor={`${uid}-source`} error={errors.source}>
            <Select
              id={`${uid}-source`}
              disabled={!enquiry.can_manage}
              value={source}
              onChange={(event) => {
                setSource(event.target.value);
                setChannel(ONLINE_SOURCES.has(event.target.value) ? "online" : "offline");
              }}
            >
              {!source ? <option value="">Not known</option> : null}
              {sourceOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Online or offline"
            htmlFor={`${uid}-channel`}
            error={errors.channel}
            hint="Follows the source; change it if the source is misleading."
          >
            <Select
              id={`${uid}-channel`}
              disabled={!enquiry.can_manage}
              value={channel}
              onChange={(event) => setChannel(event.target.value as LeadChannel)}
            >
              <option value="online">{LEAD_CHANNEL_LABEL.online}</option>
              <option value="offline">{LEAD_CHANNEL_LABEL.offline}</option>
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
      </Body>
    </Frame>
  );
}

/**
 * The enquiry's follow-up thread: what was said on each call, oldest at the
 * top, with a box to add the next one.
 *
 * A conversation, not a table. Everything else about an enquiry is a record
 * of what the *system* was told to change (the History card) or a piece of
 * scheduled work (the Activities card); this is the one place a counsellor
 * writes for whoever picks the lead up next, and it reads downwards like the
 * conversation it describes.
 *
 * Saying when the next call is moves the enquiry's own follow-up date in the
 * same act — the thing that was previously two screens apart (write the note
 * here, then remember to set the date up in Pipeline). Leaving it blank
 * leaves that date alone rather than clearing it.
 *
 * The composer is hidden for somebody who may read the enquiry but not
 * change it. That is a courtesy: `services.add_note` enforces the same right
 * on the server, and a Meritto lead takes no note at all.
 */
function FollowUpThreadCard({
  enquiry,
  onPosted,
}: {
  enquiry: EnquiryDetail;
  onPosted: () => void;
}) {
  const uid = useId();
  const [body, setBody] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  async function submit() {
    const text = body.trim();
    if (!text) {
      setErrors({ body: "Write what was said before sending." });
      return;
    }
    setSaving(true);
    setErrors({});
    try {
      await addEnquiryNote(enquiry.id, {
        body: text,
        next_follow_up_at: followUp ? new Date(followUp).toISOString() : undefined,
      });
      setBody("");
      setFollowUp("");
      onPosted();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Follow-ups</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {enquiry.notes.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No follow-up written yet. The first call, what they asked for, what was promised — it
            goes here.
          </p>
        ) : (
          <ol className="space-y-3">
            {enquiry.notes.map((note) => (
              <li key={note.id} className="rounded-card border border-line px-3 py-2">
                <p className="whitespace-pre-wrap text-sm text-ink">{note.body}</p>
                <p className="mt-1 text-2xs text-ink-faint">
                  {note.author?.name || "Automation"} · {formatDateTime(note.created_at)}
                </p>
              </li>
            ))}
          </ol>
        )}

        {enquiry.can_manage ? (
          <div className="space-y-3 border-t border-line pt-4">
            <Field label="What happened" htmlFor={`${uid}-body`} error={errors.body}>
              <Textarea
                id={`${uid}-body`}
                rows={3}
                value={body}
                onChange={(event) => setBody(event.target.value)}
                placeholder="Rang at 11. Wants the evening batch, will visit Friday."
              />
            </Field>
            <Field
              label="Next call"
              htmlFor={`${uid}-next`}
              hint="Optional. Setting it here moves the enquiry's follow-up date too, so the
              counsellor does not have to remember to change it up in Pipeline as well."
              error={errors.next_follow_up_at}
            >
              <Input
                id={`${uid}-next`}
                type="datetime-local"
                value={followUp}
                onChange={(event) => setFollowUp(event.target.value)}
              />
            </Field>
            {errors.non_field_errors ? (
              <Alert variant="error">{errors.non_field_errors}</Alert>
            ) : null}
            <Button onClick={submit} disabled={saving}>
              <Send className="size-4" aria-hidden="true" />
              {saving ? "Saving…" : "Add follow-up"}
            </Button>
          </div>
        ) : (
          <p className="border-t border-line pt-4 text-sm text-ink-muted">
            You can read this thread but not add to it.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** "23 Oct 2026, 6:50 pm – 6:55 pm" when an event has both ends, the one it
 *  has otherwise, and a dash when it is unscheduled. A booking is a span, and
 *  reading its start without its end is how two of them end up overlapping. */
function eventWhen(activity: Activity): string {
  const start = activity.planned_at;
  const end = activity.due_at;
  if (!start) return end ? formatDateTime(end) : "—";
  if (!end) return formatDateTime(start);
  const sameDay = new Date(start).toDateString() === new Date(end).toDateString();
  return sameDay
    ? `${formatDateTime(start)} – ${formatTime(end)}`
    : `${formatDateTime(start)} – ${formatDateTime(end)}`;
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
          Add Event
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
                  <Th>Event</Th>
                  <Th>Owner</Th>
                  <Th>When</Th>
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
                    <Td className="whitespace-nowrap tabular-nums">{eventWhen(row)}</Td>
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
      <AddEventDrawer
        open={logging}
        subject={{ kind: "enquiry", id: enquiry.id, name: enquiry.full_name }}
        onClose={() => setLogging(false)}
        onCreated={() => {
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

/** A Meritto lead: Meritto runs its pipeline, the LMS registers it. */
function MerittoCard({ enquiry }: { enquiry: EnquiryDetail }) {
  const facts: [string, string][] = [
    ["Stage in Meritto", enquiry.external_stage || "Not sent"],
    ["Owner in Meritto", enquiry.external_owner || "Not sent"],
    ["Meritto lead id", enquiry.external_id || "—"],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ExternalLink className="size-4 text-action" aria-hidden="true" />
          Managed in Meritto
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-ink-muted">
          Meritto sent this lead because it is ready to admit. Its stage, owner and follow-ups are
          changed in Meritto and arrive here with each update; here it is registered as a student.
        </p>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-3">
          {facts.map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-2xs font-medium uppercase tracking-wide text-ink-faint">{label}</dt>
              <dd className="truncate text-sm text-ink">{value}</dd>
            </div>
          ))}
        </dl>
        <RegistrationLine enquiry={enquiry} />
      </CardContent>
    </Card>
  );
}

/** Registered already (with a link to the student), or the way to do it. */
function RegistrationLine({ enquiry }: { enquiry: EnquiryDetail }) {
  if (enquiry.student) {
    return (
      <Alert variant="success">
        Registered as{" "}
        <Link href={`/students/${enquiry.student.id}`} className="font-medium underline">
          {enquiry.student.name || "the student"}
        </Link>
        .
      </Alert>
    );
  }
  if (!enquiry.can_register) {
    return <p className="text-sm text-ink-muted">Not registered as a student yet.</p>;
  }
  return (
    <Button asChild>
      <Link href={registerLeadHref(enquiry.id)}>
        <UserPlus className="size-4" aria-hidden="true" />
        Register this lead
      </Link>
    </Button>
  );
}

/** The forward path a lead walks. The two lost stages are not on it — a lead
 *  that went nowhere is not 70% of the way to enrolling, and drawing it as a
 *  part-filled trail would say exactly that. `StageTrail` takes them as
 *  `endedLabel` instead. */
const PIPELINE_TRAIL: StageTrailStep[] = [
  { key: "new", label: "New" },
  { key: "contacted", label: "Contacted" },
  { key: "interested", label: "Interested" },
  { key: "counselling_booked", label: "Counselling booked" },
  { key: "demo_booked", label: "Demo booked" },
  { key: "registered", label: "Registered" },
];

/** One "Label : value" line, the way the reference CRM lists a lead's fields.
 *  The colon is in its own cell rather than appended to the label, so the
 *  values line up however long the labels are. */
function DetailRows({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="divide-y divide-line">
      {rows.map(([label, value]) => (
        <div key={label} className="grid grid-cols-[minmax(9rem,14rem)_auto_1fr] gap-x-3 py-2.5">
          <dt className="text-sm text-ink-muted">{label}</dt>
          <span aria-hidden="true" className="text-sm text-ink-faint">
            :
          </span>
          <dd className="min-w-0 break-words text-sm text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** How long ago, in whole days, for the "Lead Added On" badge. */
function daysSince(iso: string): string {
  const days = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000));
  return `${days}d`;
}

/** The left-hand column: who this is, who owns it, and the three dates a
 *  counsellor is actually asked about. Everything here is a summary of what
 *  the tabs hold — the rail answers "should I be ringing this person today",
 *  the tabs answer "what happened". */
function LeadRail({
  enquiry,
  onChangeStage,
  onAddEvent,
  onAddNote,
}: {
  enquiry: EnquiryDetail;
  onChangeStage: () => void;
  onAddEvent: () => void;
  onAddNote: () => void;
}) {
  const stageLabel = enquiry.managed_externally
    ? enquiry.external_stage || "In Meritto"
    : ENQUIRY_STAGE_LABEL[enquiry.stage];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 pt-5">
          <div>
            {/* The page heading already announces the name; a second heading
                with the same text makes a screen reader read the lead twice
                and puts a phantom section in the outline. */}
            <p className="text-base font-semibold uppercase tracking-wide text-ink">
              {enquiry.full_name}
            </p>
            <p className="mt-0.5 text-sm text-ink-muted">
              Lead Stage: <span className="text-ink">{stageLabel}</span>
            </p>
          </div>
          <dl className="space-y-1.5 text-sm">
            <div className="flex items-center gap-2">
              <dt>
                <Mail className="size-4 text-ink-faint" aria-hidden="true" />
                <span className="sr-only">Email</span>
              </dt>
              <dd className="min-w-0 truncate text-ink">{enquiry.email || "Not given"}</dd>
            </div>
            <div className="flex items-center gap-2">
              <dt>
                <Phone className="size-4 text-ink-faint" aria-hidden="true" />
                <span className="sr-only">Mobile</span>
              </dt>
              <dd className="text-ink tabular-nums">{enquiry.mobile}</dd>
            </div>
          </dl>
          {enquiry.can_manage ? (
            <div className="flex flex-wrap gap-2 border-t border-line pt-3">
              <Button type="button" variant="outline" size="sm" onClick={onChangeStage}>
                <Shuffle className="size-4" aria-hidden="true" />
                Change Stage
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={onAddEvent}>
                <CalendarPlus className="size-4" aria-hidden="true" />
                Add Event
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={onAddNote}>
                <MessageSquarePlus className="size-4" aria-hidden="true" />
                Add Note
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Assignment Details</CardTitle>
        </CardHeader>
        <CardContent>
          <DetailRows
            rows={[
              [
                "Assigned Owner",
                enquiry.managed_externally
                  ? enquiry.external_owner || "In Meritto"
                  : (enquiry.owner?.name ?? "Unassigned"),
              ],
              ["Lead Source", enquiry.source || "Not known"],
              ["Online or offline", LEAD_CHANNEL_LABEL[enquiry.channel]],
              ["Lead quality", enquiry.lead_quality ? `${enquiry.lead_quality} of 5` : "Not rated"],
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Important Dates</CardTitle>
        </CardHeader>
        <CardContent>
          <DetailRows
            rows={[
              [
                "Upcoming Followup",
                enquiry.next_follow_up_at ? formatDateTime(enquiry.next_follow_up_at) : "None set",
              ],
              [
                "Last Active",
                enquiry.last_contacted_at
                  ? formatDateTime(enquiry.last_contacted_at)
                  : "Not contacted yet",
              ],
              [
                "Lead Added On",
                `${formatDateTime(enquiry.created_at)} (${daysSince(enquiry.created_at)})`,
              ],
            ]}
          />
        </CardContent>
      </Card>
    </div>
  );
}

export function EnquiryScreen({ id }: { id: string }) {
  const { user } = useAuth();
  const maySend = can(user?.capabilities, Capability.formAssign);
  const { data, error, isLoading, reload } = useApi<EnquiryDetail>(`/api/v1/enquiries/${id}/`);
  const summary = useApi<EnquirySummary>("/api/v1/enquiries/summary/");
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState("details");
  const [changingStage, setChangingStage] = useState(false);
  const [addingEvent, setAddingEvent] = useState(false);
  const notesRef = useRef<HTMLDivElement | null>(null);

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

  const lostLabel = LOST_STAGES.includes(data.stage) ? ENQUIRY_STAGE_LABEL[data.stage] : undefined;
  /** Grouped rather than one list of fourteen. The reference CRM splits these
   *  across sub-tabs (Lead Details, Walk In, Demo, Enrollment, Payment); the
   *  tabs it fills from our data would be half empty, and an empty tab is
   *  worse than a named group, so the groups are headings in one panel. */
  const factGroups: { title: string; rows: [string, string][] }[] = [
    {
      title: "Contact",
      rows: [
        ["Name", data.full_name],
        ["Email Address", data.email || "Not given"],
        ["Mobile Number", data.mobile],
        ["WhatsApp Number", data.whatsapp_number || "Same as mobile"],
        ["City", data.city || "Not given"],
        ["State", data.state || "Not given"],
      ],
    },
    {
      title: "What they asked about",
      rows: [
        ["Course", [data.course, data.track].filter(Boolean).join(" · ") || "Not given"],
        ["Centre", data.preferred_centre || "Not given"],
        ["Mode", data.mode || "Not given"],
        ["Batch timing", data.batch_timing || "Not given"],
        ["Qualification", data.qualification || "Not given"],
      ],
    },
    {
      title: "Where it came from",
      rows: [
        ["Lead Source", data.source || "Not known"],
        [
          "Campaign",
          [data.utm_source, data.utm_campaign].filter(Boolean).join(" / ") || "Not tracked",
        ],
        ["Entered by", data.created_by?.name ?? "Not recorded"],
      ],
    },
  ];

  /** Add Note is the rail's third button and the header's: both land in the
   *  thread with the composer in view, rather than opening a second place to
   *  write the same thing. */
  function goToNotes() {
    setTab("notes");
    window.requestAnimationFrame(() => {
      notesRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    });
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
        <Badge variant={data.channel === "online" ? "info" : "neutral"}>
          {LEAD_CHANNEL_LABEL[data.channel]}
        </Badge>
        {data.managed_externally ? (
          <>
            <Badge variant="info">From Meritto</Badge>
            <Badge variant={data.student ? "success" : "warning"}>
              {data.student ? "Registered" : "Ready to admit"}
            </Badge>
          </>
        ) : (
          <Badge variant={ENQUIRY_STAGE_VARIANT[data.stage]}>
            {ENQUIRY_STAGE_LABEL[data.stage]}
          </Badge>
        )}
      </PageHeader>
      {notice ? <Alert variant="success">{notice}</Alert> : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <LeadRail
          enquiry={data}
          onChangeStage={() => setChangingStage(true)}
          onAddEvent={() => setAddingEvent(true)}
          onAddNote={goToNotes}
        />

        <div className="min-w-0 space-y-4">
          <StageTrail
            steps={PIPELINE_TRAIL}
            current={data.stage}
            endedLabel={lostLabel}
            label="Lead stage"
          />

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="details">Lead Details</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              <TabsTrigger value="events">Events</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="forms">Forms</TabsTrigger>
            </TabsList>

            <TabsContent value="details" className="space-y-4 pt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Lead Details</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {factGroups.map((group) => (
                    <section key={group.title}>
                      <h3 className="mb-1 text-2xs font-semibold uppercase tracking-wide text-ink-faint">
                        {group.title}
                      </h3>
                      <DetailRows rows={group.rows} />
                    </section>
                  ))}
                  {data.remarks ? (
                    <p className="whitespace-pre-line border-t border-line pt-3 text-sm text-ink-muted">
                      {data.remarks}
                    </p>
                  ) : null}
                </CardContent>
              </Card>
              {data.managed_externally ? (
                <MerittoCard enquiry={data} />
              ) : (
                <>
                  <PipelineCard
                    key={data.updated_at}
                    enquiry={data}
                    sources={summary.data?.sources ?? []}
                    onSaved={(message) => {
                      setNotice(message);
                      reload();
                    }}
                  />
                  {data.can_register || data.student ? (
                    <Card>
                      <CardContent className="pt-5">
                        <RegistrationLine enquiry={data} />
                      </CardContent>
                    </Card>
                  ) : null}
                </>
              )}
            </TabsContent>

            <TabsContent value="timeline" className="pt-4">
              <HistoryCard enquiry={data} />
            </TabsContent>

            <TabsContent value="events" className="pt-4">
              <ActivitiesCard enquiry={data} />
            </TabsContent>

            <TabsContent value="notes" className="pt-4">
              <div ref={notesRef}>
                <FollowUpThreadCard enquiry={data} onPosted={reload} />
              </div>
            </TabsContent>

            <TabsContent value="forms" className="pt-4">
              <FormsCard enquiry={data} maySend={maySend} />
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <Dialog open={changingStage} onOpenChange={(open) => (open ? undefined : setChangingStage(false))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change Stage</DialogTitle>
            <DialogDescription>
              Where this lead stands, who owns it, and when it is next rung.
            </DialogDescription>
          </DialogHeader>
          <PipelineCard
            key={data.updated_at}
            plain
            enquiry={data}
            sources={summary.data?.sources ?? []}
            onSaved={(message) => {
              setNotice(message);
              setChangingStage(false);
              reload();
            }}
          />
        </DialogContent>
      </Dialog>

      <AddEventDrawer
        open={addingEvent}
        subject={{ kind: "enquiry", id: data.id, name: data.full_name }}
        onClose={() => setAddingEvent(false)}
        onCreated={() => {
          setAddingEvent(false);
          setTab("events");
          reload();
        }}
      />
    </div>
  );
}
