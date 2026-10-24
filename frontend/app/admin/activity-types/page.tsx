"use client";

/**
 * Activity types: the catalog behind every activity (`ACTIVITY_CATALOG.md`).
 * An administrator can add a type, disable one, or change any column except
 * `slug` — the seeded, `is_system` rows included. The field editor lives on
 * this one screen (no separate detail route): there is no version history
 * here the way a form definition has one, so a dialog is enough.
 */

import Link from "next/link";
import { useMemo, useState } from "react";
import { Eye, ListChecks, Pencil, Plus } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { RowActions } from "@/components/row-actions";
import { RequireAuth } from "@/components/require-auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Switch } from "@/components/ui/switch";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/hooks/use-api";
import { errorMessage, fieldErrors } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import { formatDateTime } from "@/lib/format";
import {
  ACTIVITY_CATEGORY_LABEL,
  ACTIVITY_CATEGORY_OPTIONS,
  ACTIVITY_RISK_EFFECT_LABEL,
  ACTIVITY_TYPE_STATUS_LABEL,
  ACTIVITY_TYPE_STATUS_VARIANT,
  ROLE_LABEL,
} from "@/lib/labels";
import type { FormDefinitionListResponse } from "@/lib/forms";
import { slugify } from "@/lib/roles";
import {
  createActivityType,
  updateActivityType,
  type ActivityTypeInput,
  type ActivityTypeListResponse,
} from "@/lib/work";
import type {
  ActivityCategory,
  ActivityRiskEffect,
  ActivityType,
  UserRole,
} from "@/types/api";

const ASSIGNABLE_ROLES: UserRole[] = [
  "trainer",
  "counsellor",
  "manager",
  "admin",
  "superadmin",
  "student",
];

function blankInput(): ActivityTypeInput {
  return {
    slug: "",
    name: "",
    description: "",
    category: "other",
    allowed_creator_roles: [],
    allowed_assignee_roles: [],
    visible_to_student: false,
    default_duration_minutes: null,
    form: null,
    requires_review: false,
    performance_weight: "0",
    risk_effect: "none",
    reminder_minutes_before: null,
    status: "active",
    check_conflict: false,
    // On unless turned off, matching the server's default: reopening a
    // completed activity is behaviour trainers already rely on.
    reopen_allowed: true,
    invite_organiser: false,
    invite_owner: false,
  };
}

function toInput(type: ActivityType): ActivityTypeInput {
  return {
    slug: type.slug,
    name: type.name,
    description: type.description,
    category: type.category,
    allowed_creator_roles: type.allowed_creator_roles,
    allowed_assignee_roles: type.allowed_assignee_roles,
    visible_to_student: type.visible_to_student,
    default_duration_minutes: type.default_duration_minutes,
    // The API sends the pinned form's slug and takes the same slug back, so
    // this is a pass-through. It used to read `type.form?.id`, against a
    // declaration that said `{id, slug}` — on a string that is `undefined`,
    // so every edit of a type with a form quietly unpinned it.
    form: type.form,
    requires_review: type.requires_review,
    performance_weight: type.performance_weight,
    risk_effect: type.risk_effect,
    reminder_minutes_before: type.reminder_minutes_before,
    status: type.status,
    check_conflict: type.check_conflict,
    reopen_allowed: type.reopen_allowed,
    invite_organiser: type.invite_organiser,
    invite_owner: type.invite_owner,
  };
}

/**
 * A checkbox group over `UserRole` — used for both allowed-role fields.
 *
 * Its error is wired to the group the same way `Field` wires one to an
 * `<input>` (`aria-describedby` on the group, an `id`-matched message right
 * below it) rather than as a bare, unconnected `<p>` — this group isn't an
 * `<input>` `Field` can clone props onto, so the same contract is applied
 * by hand instead.
 */
function RoleCheckboxes({
  legend,
  groupId,
  values,
  onChange,
  error,
}: {
  legend: string;
  /** Unique per group, so its own error has a stable id to point at. */
  groupId: string;
  values: string[];
  onChange: (next: string[]) => void;
  error?: string;
}) {
  const selected = new Set(values);
  const errorId = `${groupId}-error`;
  return (
    <div className="space-y-1.5">
      <div
        className="space-y-1.5"
        role="group"
        aria-label={legend}
        aria-describedby={error ? errorId : undefined}
      >
        <p className="text-sm font-medium">{legend}</p>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          {ASSIGNABLE_ROLES.map((role) => (
            <label key={role} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={selected.has(role)}
                onCheckedChange={(checked) => {
                  const next = new Set(selected);
                  if (checked) next.add(role);
                  else next.delete(role);
                  onChange(Array.from(next));
                }}
              />
              {ROLE_LABEL[role]}
            </label>
          ))}
        </div>
      </div>
      {error ? (
        <p id={errorId} className="text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ActivityTypeDialog({
  open,
  editing,
  formOptions,
  onClose,
  onSaved,
}: {
  open: boolean;
  editing: ActivityType | null;
  formOptions: { slug: string; name: string }[];
  onClose: () => void;
  onSaved: (type: ActivityType) => void;
}) {
  const [input, setInput] = useState<ActivityTypeInput>(() =>
    editing ? toInput(editing) : blankInput(),
  );
  const [slugTouched, setSlugTouched] = useState(Boolean(editing));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  // Reset the form to match whichever record this dialog opened for. Keyed
  // on `open`/`editing?.slug` rather than run unconditionally, so typing
  // inside the dialog is never clobbered by an unrelated re-render.
  const resetKey = `${open}#${editing?.slug ?? "new"}`;
  const [openedFor, setOpenedFor] = useState(resetKey);
  if (openedFor !== resetKey) {
    setInput(editing ? toInput(editing) : blankInput());
    setSlugTouched(Boolean(editing));
    setErrors({});
    setOpenedFor(resetKey);
  }

  const isEdit = Boolean(editing);

  // Real progressive disclosure for the one form in the app that genuinely
  // dumped all ~15 fields on one screen at once (R1's audit finding). Native
  // <details>/<summary> again, not a new primitive — same convention
  // `app/students/[id]/page.tsx` already uses for the same reason: this
  // codebase's `components/ui/*` has no collapsible yet, and inventing one
  // for two call sites is a bigger change than this phase's brief allows.
  // Only Name/Slug/Description/Category (the four most load-bearing, and the
  // only three that are ever `required`) stay unconditionally visible; the
  // rest is staged behind three sections a person opens when it is relevant
  // to what they are doing.
  //
  // A section starts open when editing an existing type (so nothing already
  // set is hidden from someone who came here to change it) and starts
  // closed for a new one (so creating a type shows the essentials first).
  // Either way, a section forces itself open the moment the server returns
  // an error for one of its own fields, so a validation failure is never
  // hidden inside a collapsed section — and, because that computed value
  // only changes when `isEdit` or the error itself changes, a person can
  // still freely collapse a section by hand afterwards without React
  // fighting the click on the next unrelated re-render.
  const assignmentHasError = Boolean(errors.allowed_creator_roles || errors.allowed_assignee_roles);
  const schedulingHasError = Boolean(
    errors.default_duration_minutes || errors.reminder_minutes_before || errors.form,
  );
  const scoringHasError = Boolean(errors.performance_weight || errors.risk_effect || errors.status);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      const saved = isEdit
        ? await updateActivityType(editing!.slug, input)
        : await createActivityType(input);
      onSaved(saved);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <form className="space-y-4" onSubmit={(event) => void submit(event)} noValidate>
          <DialogHeader>
            <DialogTitle>{isEdit ? `Edit ${editing!.name}` : "New activity type"}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Every column may change except the slug, including for a seeded type."
                : "Defines the shape of a piece of work: who may create and be assigned it, its pinned form, and how it counts toward performance and risk."}
            </DialogDescription>
          </DialogHeader>

          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

          <Field label="Name" htmlFor="at-name" error={errors.name} required>
            <Input
              id="at-name"
              autoFocus
              value={input.name}
              onChange={(event) => {
                const value = event.target.value;
                setInput((current) => ({
                  ...current,
                  name: value,
                  slug: slugTouched ? current.slug : slugify(value),
                }));
              }}
            />
          </Field>

          <Field
            label="Slug"
            htmlFor="at-slug"
            error={errors.slug}
            required
            hint={isEdit ? "Fixed once created." : "Used in the API and in every reference to this type."}
          >
            <Input
              id="at-slug"
              value={input.slug}
              disabled={isEdit}
              onChange={(event) => {
                setSlugTouched(true);
                setInput((current) => ({ ...current, slug: event.target.value }));
              }}
            />
          </Field>

          <Field label="Description" htmlFor="at-description" error={errors.description}>
            <Textarea
              id="at-description"
              value={input.description}
              onChange={(event) =>
                setInput((current) => ({ ...current, description: event.target.value }))
              }
            />
          </Field>

          <Field label="Category" htmlFor="at-category" error={errors.category} required>
            <Select
              id="at-category"
              value={input.category}
              onChange={(event) =>
                setInput((current) => ({
                  ...current,
                  category: event.target.value as ActivityCategory,
                }))
              }
            >
              {ACTIVITY_CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          <details
            className="space-y-4 rounded-card border border-line p-3"
            open={isEdit || assignmentHasError}
          >
            <summary className="cursor-pointer select-none text-sm font-medium hover:text-ink">
              Who can do this, and who sees it
            </summary>
            <div className="space-y-4 pt-3">
              {/* The one real grouping this form already implies (per the R1
                  audit): both role-checkbox groups answer the same "who" the
                  file's own docstring names ("who may create and be assigned
                  it") — grouped under one shared heading rather than sitting
                  as two unrelated fields among the other ~13. */}
              <fieldset className="space-y-4 rounded-card border border-line p-3">
                <legend className="px-1 text-sm font-medium">Roles</legend>
                <RoleCheckboxes
                  legend="Who may create it"
                  groupId="at-creator-roles"
                  values={input.allowed_creator_roles}
                  onChange={(next) =>
                    setInput((current) => ({ ...current, allowed_creator_roles: next }))
                  }
                  error={errors.allowed_creator_roles}
                />
                <RoleCheckboxes
                  legend="Who may be assigned it"
                  groupId="at-assignee-roles"
                  values={input.allowed_assignee_roles}
                  onChange={(next) =>
                    setInput((current) => ({ ...current, allowed_assignee_roles: next }))
                  }
                  error={errors.allowed_assignee_roles}
                />
              </fieldset>

              <div className="flex items-center justify-between rounded-md border border-line p-3">
                <div>
                  <p className="text-sm font-medium">Visible to the student</p>
                  <p className="text-xs text-ink-muted">
                    An activity of this type may still be hidden on its own; it can never be
                    made visible when the type is not.
                  </p>
                </div>
                <Switch
                  checked={input.visible_to_student}
                  onCheckedChange={(checked) =>
                    setInput((current) => ({ ...current, visible_to_student: checked }))
                  }
                />
              </div>
            </div>
          </details>

          <details
            className="space-y-4 rounded-card border border-line p-3"
            open={isEdit || schedulingHasError}
          >
            <summary className="cursor-pointer select-none text-sm font-medium hover:text-ink">
              Scheduling and its form
            </summary>
            <div className="space-y-4 pt-3">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Default duration (minutes)"
                  htmlFor="at-duration"
                  error={errors.default_duration_minutes}
                >
                  <Input
                    id="at-duration"
                    type="number"
                    min={0}
                    value={input.default_duration_minutes ?? ""}
                    onChange={(event) =>
                      setInput((current) => ({
                        ...current,
                        default_duration_minutes:
                          event.target.value === "" ? null : Number(event.target.value),
                      }))
                    }
                  />
                </Field>
                <Field
                  label="Reminder (minutes before)"
                  htmlFor="at-reminder"
                  error={errors.reminder_minutes_before}
                >
                  <Input
                    id="at-reminder"
                    type="number"
                    min={0}
                    value={input.reminder_minutes_before ?? ""}
                    onChange={(event) =>
                      setInput((current) => ({
                        ...current,
                        reminder_minutes_before:
                          event.target.value === "" ? null : Number(event.target.value),
                      }))
                    }
                  />
                </Field>
              </div>

              <Field
                label="Form"
                htmlFor="at-form"
                error={errors.form}
                hint="Pinned at creation for every activity of this type."
              >
                <Select
                  id="at-form"
                  value={input.form ?? ""}
                  onChange={(event) =>
                    setInput((current) => ({
                      ...current,
                      form: event.target.value || null,
                    }))
                  }
                >
                  <option value="">No form</option>
                  {formOptions.map((form) => (
                    <option key={form.slug} value={form.slug}>
                      {form.name}
                    </option>
                  ))}
                </Select>
              </Field>

              <div className="flex items-center justify-between rounded-md border border-line p-3">
                <div>
                  <p className="text-sm font-medium">Requires review</p>
                  <p className="text-xs text-ink-muted">
                    Completion goes to Under review instead of Completed.
                  </p>
                </div>
                <Switch
                  checked={input.requires_review}
                  onCheckedChange={(checked) =>
                    setInput((current) => ({ ...current, requires_review: checked }))
                  }
                />
              </div>
            </div>
          </details>

          <details
            className="space-y-4 rounded-card border border-line p-3"
            open={isEdit || Boolean(errors.check_conflict || errors.reopen_allowed)}
          >
            <summary className="cursor-pointer select-none text-sm font-medium hover:text-ink">
              Booking and invitations
            </summary>
            <div className="space-y-4 pt-3">
              <div className="flex items-center justify-between rounded-md border border-line p-3">
                <div>
                  <p className="text-sm font-medium">Check conflict</p>
                  <p className="text-xs text-ink-muted">
                    Refuse a second one of these at the same time for the same person. Two
                    follow-up calls at once is a busy morning; two mock interviews with one
                    trainer is a mistake.
                  </p>
                </div>
                <Switch
                  aria-label="Check conflict"
                  checked={input.check_conflict}
                  onCheckedChange={(checked) =>
                    setInput((current) => ({ ...current, check_conflict: checked }))
                  }
                />
              </div>

              <div className="flex items-center justify-between rounded-md border border-line p-3">
                <div>
                  <p className="text-sm font-medium">Open completed event</p>
                  <p className="text-xs text-ink-muted">
                    Allow a completed one to be opened again. Turn it off where done must mean
                    done. Reopening something missed or cancelled stays available either way.
                  </p>
                </div>
                <Switch
                  aria-label="Open completed event"
                  checked={input.reopen_allowed}
                  onCheckedChange={(checked) =>
                    setInput((current) => ({ ...current, reopen_allowed: checked }))
                  }
                />
              </div>

              <div className="space-y-3 rounded-md border border-line p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium">Send invite to organiser</p>
                  <Switch
                    aria-label="Send invite to organiser"
                    checked={input.invite_organiser}
                    onCheckedChange={(checked) =>
                      setInput((current) => ({ ...current, invite_organiser: checked }))
                    }
                  />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium">Send invite to owner</p>
                  <Switch
                    aria-label="Send invite to owner"
                    checked={input.invite_owner}
                    onCheckedChange={(checked) =>
                      setInput((current) => ({ ...current, invite_owner: checked }))
                    }
                  />
                </div>
                {input.invite_organiser || input.invite_owner ? (
                  <Alert variant="warning">
                    Recorded, not sent. Calendar invitations are not wired to a mail calendar
                    yet, so nothing leaves the system — the setting is kept so it takes effect
                    the day they are.
                  </Alert>
                ) : null}
              </div>
            </div>
          </details>

          <details
            className="space-y-4 rounded-card border border-line p-3"
            open={isEdit || scoringHasError}
          >
            <summary className="cursor-pointer select-none text-sm font-medium hover:text-ink">
              Scoring{isEdit ? " and status" : ""}
            </summary>
            <div className="space-y-4 pt-3">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Performance weight"
                  htmlFor="at-weight"
                  error={errors.performance_weight}
                  hint="0 = no effect on the performance component."
                >
                  <Input
                    id="at-weight"
                    type="number"
                    min={0}
                    max={99.99}
                    step="0.1"
                    value={input.performance_weight}
                    onChange={(event) =>
                      setInput((current) => ({
                        ...current,
                        performance_weight: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field label="Risk effect" htmlFor="at-risk" error={errors.risk_effect}>
                  <Select
                    id="at-risk"
                    value={input.risk_effect}
                    onChange={(event) =>
                      setInput((current) => ({
                        ...current,
                        risk_effect: event.target.value as ActivityRiskEffect,
                      }))
                    }
                  >
                    {(Object.keys(ACTIVITY_RISK_EFFECT_LABEL) as ActivityRiskEffect[]).map(
                      (value) => (
                        <option key={value} value={value}>
                          {ACTIVITY_RISK_EFFECT_LABEL[value]}
                        </option>
                      ),
                    )}
                  </Select>
                </Field>
              </div>

              {isEdit ? (
                <Field label="Status" htmlFor="at-status" error={errors.status}>
                  <Select
                    id="at-status"
                    value={input.status}
                    onChange={(event) =>
                      setInput((current) => ({
                        ...current,
                        status: event.target.value as "active" | "disabled",
                      }))
                    }
                  >
                    <option value="active">{ACTIVITY_TYPE_STATUS_LABEL.active}</option>
                    <option value="disabled">{ACTIVITY_TYPE_STATUS_LABEL.disabled}</option>
                  </Select>
                </Field>
              ) : null}
            </div>
          </details>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving || !input.name.trim() || !input.slug.trim()}>
              {saving ? "Saving…" : isEdit ? "Save changes" : "Create type"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ActivityTypesList() {
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.activityTypeManage);

  const { data, error, isLoading, reload } =
    useApi<ActivityTypeListResponse>("/api/v1/activity-types/");
  const { data: formsData } = useApi<FormDefinitionListResponse>("/api/v1/forms/");

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ActivityType | null>(null);
  const [tab, setTab] = useState("events");
  const [toggling, setToggling] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const formOptions = useMemo(
    () =>
      (formsData?.results ?? [])
        .filter((form) => form.entity === "activity" && Boolean(form.slug))
        .map((form) => ({ slug: form.slug, name: form.name })),
    [formsData],
  );

  const rows = data?.results ?? [];

  function openCreate() {
    setEditing(null);
    setDialogOpen(true);
  }

  function openEdit(type: ActivityType) {
    setEditing(type);
    setDialogOpen(true);
  }

  /** The row's own switch, the way the reference CRM's Calendar Pro list
   *  works: an event is turned off where it stands, without opening it. The
   *  row shows the new state only once the server has agreed to it. */
  async function toggleStatus(type: ActivityType, active: boolean) {
    setToggling(type.slug);
    setFailure(null);
    try {
      await updateActivityType(type.slug, { status: active ? "active" : "disabled" });
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause));
    } finally {
      setToggling(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Calendar Pro</h1>
          <p className="text-sm text-ink-muted">
            Every kind of event and piece of staff work — follow-ups, centre visits, technical
            talks with a trainer, mock interviews, reviews — with who may create and be assigned
            each, the fields it asks for, and how it feeds performance and risk.
          </p>
        </div>
        {mayManage ? (
          <Button type="button" onClick={openCreate}>
            <Plus className="size-4" aria-hidden="true" />
            New Event
          </Button>
        ) : null}
      </div>

      {failure ? <Alert variant="error">{failure}</Alert> : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="events">Events</TabsTrigger>
          <TabsTrigger value="fields">Fields</TabsTrigger>
        </TabsList>

        <TabsContent value="events" className="pt-4">
          {isLoading ? (
            <LoadingState label="Loading events…" rows={6} />
          ) : error ? (
            <ErrorState
              title="Could not load events"
              message={error.message}
              requestId={error.requestId || undefined}
              onRetry={reload}
            />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No events yet"
              description="Create the first one to start booking and assigning work."
              action={
                mayManage ? (
                  <Button type="button" onClick={openCreate}>
                    <Plus className="size-4" aria-hidden="true" />
                    New Event
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    <Th>Event Name</Th>
                    <Th>Created By</Th>
                    <Th>Created On</Th>
                    <Th>Updated By</Th>
                    <Th>Updated On</Th>
                    <Th>Status</Th>
                    <Th>
                      <span className="sr-only">Action</span>
                    </Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.slug} className="hover:bg-sunken/40">
                      <Td>
                        <p className="font-medium">{row.name}</p>
                        <p className="text-xs text-ink-muted">
                          {ACTIVITY_CATEGORY_LABEL[row.category]}
                          {row.form ? ` · ${row.form}` : " · no fields"}
                          {row.check_conflict ? " · checks for a clash" : ""}
                        </p>
                      </Td>
                      <Td>{row.created_by_name || "—"}</Td>
                      <Td className="whitespace-nowrap tabular-nums">
                        {formatDateTime(row.created_at)}
                      </Td>
                      <Td>{row.updated_by_name || "—"}</Td>
                      <Td className="whitespace-nowrap tabular-nums">
                        {formatDateTime(row.updated_at)}
                      </Td>
                      <Td>
                        {mayManage ? (
                          <Switch
                            aria-label={`${row.name} is active`}
                            checked={row.status === "active"}
                            disabled={toggling === row.slug}
                            onCheckedChange={(checked) => void toggleStatus(row, checked)}
                          />
                        ) : (
                          <Badge variant={ACTIVITY_TYPE_STATUS_VARIANT[row.status]}>
                            {ACTIVITY_TYPE_STATUS_LABEL[row.status]}
                          </Badge>
                        )}
                      </Td>
                      <Td>
                        <RowActions
                          subject={row.name}
                          actions={[
                            {
                              label: "Edit Event",
                              icon: Pencil,
                              capability: Capability.activityTypeManage,
                              onSelect: () => openEdit(row),
                            },
                            {
                              label: "Manage Fields",
                              icon: ListChecks,
                              capability: Capability.formManage,
                              href: row.form ? `/admin/forms/${row.form}` : "/admin/forms",
                              disabledReason: row.form
                                ? undefined
                                : "This event asks for no fields yet. Pin a form to it first.",
                            },
                            {
                              label: "View Activities",
                              icon: Eye,
                              href: `/activities?type=${encodeURIComponent(row.slug)}`,
                            },
                          ]}
                        />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
          )}
        </TabsContent>

        <TabsContent value="fields" className="space-y-4 pt-4">
          <p className="text-sm text-ink-muted">
            The field sets events ask for. Each is a form, built and published in the form
            builder; an event pins one, and every activity of that event asks exactly those
            questions.
          </p>
          {formOptions.length === 0 ? (
            <EmptyState
              title="No event fields yet"
              description="Build a field set in the form builder, then pin it to an event."
              action={
                <Button asChild variant="outline">
                  <Link href="/admin/forms">Open the form builder</Link>
                </Button>
              }
            />
          ) : (
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    <Th>Field set</Th>
                    <Th>Used by</Th>
                    <Th>
                      <span className="sr-only">Action</span>
                    </Th>
                  </tr>
                </thead>
                <tbody>
                  {formOptions.map((form) => {
                    const users = rows.filter((row) => row.form === form.slug);
                    return (
                      <tr key={form.slug} className="hover:bg-sunken/40">
                        <Td>
                          <p className="font-medium">{form.name}</p>
                          <p className="text-xs text-ink-muted">{form.slug}</p>
                        </Td>
                        <Td>
                          {users.length === 0 ? (
                            <span className="text-ink-muted">No event yet</span>
                          ) : (
                            users.map((row) => row.name).join(", ")
                          )}
                        </Td>
                        <Td className="text-right">
                          <Button asChild size="sm" variant="outline">
                            <Link href={`/admin/forms/${form.slug}`}>Manage Fields</Link>
                          </Button>
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </TableWrapper>
          )}
        </TabsContent>
      </Tabs>

      <ActivityTypeDialog
        open={dialogOpen}
        editing={editing}
        formOptions={formOptions}
        onClose={() => setDialogOpen(false)}
        onSaved={() => {
          setDialogOpen(false);
          reload();
        }}
      />
    </div>
  );
}

export default function ActivityTypesPage() {
  return (
    <RequireAuth capability={Capability.activityTypeManage}>
      <ActivityTypesList />
    </RequireAuth>
  );
}
