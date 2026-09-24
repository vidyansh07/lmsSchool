"use client";

/**
 * Activity types: the catalog behind every activity (`ACTIVITY_CATALOG.md`).
 * An administrator can add a type, disable one, or change any column except
 * `slug` — the seeded, `is_system` rows included. The field editor lives on
 * this one screen (no separate detail route): there is no version history
 * here the way a form definition has one, so a dialog is enough.
 */

import { useMemo, useState } from "react";
import { Plus } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
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
import { useApi } from "@/hooks/use-api";
import { fieldErrors } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
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
    // `ActivityType.form` reads back as `{id, slug}`; every write takes the
    // bare id (`ActivityTypeCreateSerializer`/`...PatchSerializer`'s `form`
    // is a `UUIDField`).
    form: type.form?.id ?? null,
    requires_review: type.requires_review,
    performance_weight: type.performance_weight,
    risk_effect: type.risk_effect,
    reminder_minutes_before: type.reminder_minutes_before,
    status: type.status,
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
        <p id={errorId} className="text-xs text-destructive">
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
  formOptions: { id: string; name: string }[];
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
            className="space-y-4 rounded-card border border-border p-3"
            open={isEdit || assignmentHasError}
          >
            <summary className="cursor-pointer select-none text-sm font-medium hover:text-foreground">
              Who can do this, and who sees it
            </summary>
            <div className="space-y-4 pt-3">
              {/* The one real grouping this form already implies (per the R1
                  audit): both role-checkbox groups answer the same "who" the
                  file's own docstring names ("who may create and be assigned
                  it") — grouped under one shared heading rather than sitting
                  as two unrelated fields among the other ~13. */}
              <fieldset className="space-y-4 rounded-card border border-border p-3">
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

              <div className="flex items-center justify-between rounded-md border border-border p-3">
                <div>
                  <p className="text-sm font-medium">Visible to the student</p>
                  <p className="text-xs text-muted-foreground">
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
            className="space-y-4 rounded-card border border-border p-3"
            open={isEdit || schedulingHasError}
          >
            <summary className="cursor-pointer select-none text-sm font-medium hover:text-foreground">
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
                    <option key={form.id} value={form.id}>
                      {form.name}
                    </option>
                  ))}
                </Select>
              </Field>

              <div className="flex items-center justify-between rounded-md border border-border p-3">
                <div>
                  <p className="text-sm font-medium">Requires review</p>
                  <p className="text-xs text-muted-foreground">
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
            className="space-y-4 rounded-card border border-border p-3"
            open={isEdit || scoringHasError}
          >
            <summary className="cursor-pointer select-none text-sm font-medium hover:text-foreground">
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

  const formOptions = useMemo(
    () =>
      (formsData?.results ?? [])
        .filter(
          (form): form is typeof form & { id: string } =>
            form.entity === "activity" && Boolean(form.id),
        )
        .map((form) => ({ id: form.id, name: form.name })),
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Activity types</h1>
          <p className="text-sm text-muted-foreground">
            The catalog behind every piece of staff work — interviews, mentoring,
            reviews, placement calls and the rest — with who may create and be
            assigned each, its pinned form, and how it feeds performance and risk.
          </p>
        </div>
        {mayManage ? (
          <Button type="button" onClick={openCreate}>
            <Plus className="size-4" aria-hidden="true" />
            New type
          </Button>
        ) : null}
      </div>

      {isLoading ? (
        <LoadingState label="Loading activity types…" rows={6} />
      ) : error ? (
        <ErrorState
          title="Could not load activity types"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={reload}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No activity types yet"
          description="Create the first type to start assigning work."
          action={
            mayManage ? (
              <Button type="button" onClick={openCreate}>
                <Plus className="size-4" aria-hidden="true" />
                New type
              </Button>
            ) : undefined
          }
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Type</Th>
                <Th>Category</Th>
                <Th>Form</Th>
                <Th>Review</Th>
                <Th>Weight</Th>
                <Th>Status</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.slug} className="hover:bg-muted/40">
                  <Td>
                    <p className="font-medium">{row.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {row.slug}
                      {row.is_system ? " · seeded" : ""}
                    </p>
                  </Td>
                  <Td>
                    <Badge>
                      {ACTIVITY_CATEGORY_LABEL[row.category]}
                    </Badge>
                  </Td>
                  <Td>
                    {row.form ? (
                      row.form.slug
                    ) : (
                      <span className="text-muted-foreground">None</span>
                    )}
                  </Td>
                  <Td>{row.requires_review ? "Yes" : "No"}</Td>
                  <Td>{row.performance_weight}</Td>
                  <Td>
                    <Badge variant={ACTIVITY_TYPE_STATUS_VARIANT[row.status]}>
                      {ACTIVITY_TYPE_STATUS_LABEL[row.status]}
                    </Badge>
                  </Td>
                  <Td className="text-right">
                    {mayManage ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => openEdit(row)}
                      >
                        Edit
                      </Button>
                    ) : null}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}

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
