"use client";

/**
 * The action list editor for one `AutomationRule` (`docs/erp/
 * AUTOMATION_CATALOG.md` "Actions"). Each action type has its
 * own fixed parameter shape — this file is the one place a type is mapped to
 * its form, mirroring `components/forms/field-editor.tsx`'s per-field-type
 * switch (`validationKeysFor`/the type-specific rows in `FieldRow`) rather
 * than inventing a second pattern for "one form shape per enum value".
 *
 * A `to`/`assign_to`/`reviewer` param is a *strategy* — a named keyword
 * `apps.automation.resolve.resolve_user` resolves to a real person — or a
 * literal id/role/address; `StrategyField` offers the named ones from
 * `lib/automation.ts` and falls back to free text for anything else,
 * exactly like `field-editor.tsx`'s relation-model select never blocks a
 * value it does not have a friendly label for.
 */

import { useId } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { usePublishedFields } from "@/components/automation/use-published-fields";
import {
  ASSIGN_TO_STRATEGIES,
  ENQUIRY_OWNER_STRATEGIES,
  FORM_RECIPIENT_STRATEGIES,
  NOTIFICATION_TO_STRATEGIES,
  REVIEWER_STRATEGIES,
} from "@/lib/automation";
import {
  ACTIVITY_PRIORITY_LABEL,
  AUTOMATION_ACTION_TYPE_OPTIONS,
  ENQUIRY_STAGE_LABEL,
  ENQUIRY_STAGES,
  ROLE_OPTIONS,
} from "@/lib/labels";
import type {
  ActivityPriority,
  AssignFormActionParams,
  AutomationAction,
  AutomationActionType,
  CreateActivityActionParams,
  CreateReviewActionParams,
  FlagRiskActionParams,
  SendEmailActionParams,
  SendNotificationActionParams,
  SendWhatsappActionParams,
  UpdateEnquiryActionParams,
} from "@/types/api";

/** An activity type as the action editor needs it: what it is about, and
 *  the form its completion is answered with (for pre-filled answers). */
export interface ActivityTypeOption {
  slug: string;
  name: string;
  subject?: "student" | "enquiry";
  form?: string | null;
}

const OTHER_STRATEGY = "__other__";

/** A select over a fixed set of named strategies, plus free text for a
 *  literal id, role slug or address the fixed set does not name. Never
 *  blocks a value already on the rule that the fixed set does not know —
 *  the select simply shows "Other" and the text field carries it. */
function StrategyField({
  id,
  label,
  hint,
  value,
  options,
  otherLabel,
  onChange,
  disabled,
  allowOther = true,
}: {
  id: string;
  label: string;
  hint?: string;
  value: string;
  options: { value: string; label: string }[];
  otherLabel: string;
  onChange: (value: string) => void;
  disabled: boolean;
  /** False when the fixed options are the only sensible answers. */
  allowOther?: boolean;
}) {
  const isKnown = !allowOther || options.some((option) => option.value === value);
  return (
    // `Field` clones its id/aria-* onto a *single* child element; the
    // conditional "Other" input has to sit outside that (as a sibling), not
    // nested inside one more wrapping `<div>`, or `Field` clones those
    // attributes onto the div instead of the actual, labellable `<select>`.
    <div className="space-y-2">
      <Field label={label} htmlFor={id} hint={hint}>
        <Select
          disabled={disabled}
          value={isKnown ? value : OTHER_STRATEGY}
          onChange={(event) => {
            const next = event.target.value;
            onChange(next === OTHER_STRATEGY ? "" : next);
          }}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
          {allowOther ? <option value={OTHER_STRATEGY}>{otherLabel}</option> : null}
        </Select>
      </Field>
      {!isKnown ? (
        <Input
          aria-label={otherLabel}
          value={value}
          disabled={disabled}
          placeholder="User ID"
          onChange={(event) => onChange(event.target.value)}
        />
      ) : null}
    </div>
  );
}

/** Each branch's `type` is a string literal, so the object it returns is
 *  narrowed to that one member of `AutomationAction` — no cast needed at the
 *  call sites below. */
function blankActionFor(type: AutomationActionType): AutomationAction {
  switch (type) {
    case "create_activity":
      return {
        type: "create_activity",
        params: { type: "", assign_to: "same_assignee", due_in_days: 7, priority: "", title: "" },
      };
    case "send_notification":
      return {
        type: "send_notification",
        params: { to: "manager", kind: "", title: "", body: "" },
      };
    case "send_email":
      return { type: "send_email", params: { to: "manager", template: "" } };
    case "send_whatsapp":
      return { type: "send_whatsapp", params: { to: "manager", template: "" } };
    case "create_review":
      return {
        type: "create_review",
        params: { review_type: "ad_hoc", reviewer: "manager", due_in_days: 7 },
      };
    case "flag_risk":
      return { type: "flag_risk", params: { level: "warning", reason: "" } };
    case "assign_form":
      return {
        type: "assign_form",
        params: { form: "", to: "submitter", due_in_days: 1, title: "", message: "" },
      };
    case "update_enquiry":
      return { type: "update_enquiry", params: { stage: "", owner: "" } };
  }
}

/** The `{{path}}` variables a title or message can use for this rule — the
 *  trigger form's answers first, since those are what a person most often
 *  wants to quote. */
function VariableHint({ variables }: { variables: string[] }) {
  if (variables.length === 0) return null;
  return (
    <p className="text-2xs text-ink-faint">
      You can use:{" "}
      {variables.map((variable, index) => (
        <span key={variable}>
          {index > 0 ? ", " : ""}
          <code className="rounded bg-sunken px-1 font-mono text-ink-muted">{`{{${variable}}}`}</code>
        </span>
      ))}
    </p>
  );
}

function AssignFormFields({
  params,
  formOptions,
  variables,
  onChange,
  disabled,
}: {
  params: AssignFormActionParams;
  formOptions: { slug: string; name: string }[];
  variables: string[];
  onChange: (next: AssignFormActionParams) => void;
  disabled: boolean;
}) {
  const uid = useId();
  const known = formOptions.some((option) => option.slug === params.form);
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field
        label="Form to send"
        htmlFor={`${uid}-form`}
        hint="A published enquiry or general form. Activity forms are filled in from their activity."
      >
        <Select
          id={`${uid}-form`}
          disabled={disabled}
          value={params.form}
          onChange={(event) => onChange({ ...params, form: event.target.value })}
        >
          <option value="">Select a form…</option>
          {!known && params.form ? (
            <option value={params.form}>{params.form} (not available)</option>
          ) : null}
          {formOptions.map((option) => (
            <option key={option.slug} value={option.slug}>
              {option.name}
            </option>
          ))}
        </Select>
      </Field>
      <StrategyField
        id={`${uid}-to`}
        label="Who fills it in"
        value={params.to}
        options={FORM_RECIPIENT_STRATEGIES}
        otherLabel="A specific person (user ID)"
        disabled={disabled}
        onChange={(value) => onChange({ ...params, to: value })}
      />
      <Field label="Due in (days)" htmlFor={`${uid}-due`} hint="Leave blank for no due date.">
        <Input
          id={`${uid}-due`}
          type="number"
          min={0}
          disabled={disabled}
          value={params.due_in_days ?? ""}
          onChange={(event) =>
            onChange({
              ...params,
              due_in_days: event.target.value === "" ? null : Number(event.target.value),
            })
          }
        />
      </Field>
      <Field label="Title" htmlFor={`${uid}-title`} hint="Leave blank to use the form's name.">
        <Input
          id={`${uid}-title`}
          disabled={disabled}
          value={params.title ?? ""}
          onChange={(event) => onChange({ ...params, title: event.target.value })}
        />
      </Field>
      <Field label="Message" htmlFor={`${uid}-message`} className="sm:col-span-2">
        <Textarea
          id={`${uid}-message`}
          rows={2}
          disabled={disabled}
          value={params.message ?? ""}
          onChange={(event) => onChange({ ...params, message: event.target.value })}
        />
      </Field>
      <div className="sm:col-span-2">
        <VariableHint variables={variables} />
      </div>
    </div>
  );
}

function NumberField({
  id,
  label,
  hint,
  value,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  hint?: string;
  value: number | null | undefined;
  disabled: boolean;
  onChange: (value: number | null) => void;
}) {
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <Input
        id={id}
        type="number"
        min={0}
        disabled={disabled}
        value={value ?? ""}
        onChange={(event) =>
          onChange(event.target.value === "" ? null : Number(event.target.value))
        }
      />
    </Field>
  );
}

/** "Create an activity": which kind, who does it, when, and its content —
 *  title, notes and answers to its form filled in ahead, each one able to
 *  quote the trigger, e.g. `{{enquiry.full_name}}`. */
function CreateActivityFields({
  params,
  activityTypeOptions,
  variables,
  onChange,
  disabled,
}: {
  params: CreateActivityActionParams;
  activityTypeOptions: ActivityTypeOption[];
  variables: string[];
  onChange: (next: CreateActivityActionParams) => void;
  disabled: boolean;
}) {
  const uid = useId();
  const chosen = activityTypeOptions.find((option) => option.slug === params.type);
  const formFields = usePublishedFields(chosen?.form ?? null).filter(
    (field) => field.type !== "file" && field.type !== "image",
  );
  const prefill = params.form_prefill ?? {};
  const byRecord = {
    enquiry: activityTypeOptions.filter((option) => option.subject === "enquiry"),
    student: activityTypeOptions.filter((option) => option.subject !== "enquiry"),
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field
          label="Activity type"
          htmlFor={`${uid}-type`}
          hint={
            chosen
              ? chosen.subject === "enquiry"
                ? "About the trigger's enquiry."
                : "About the trigger's student."
              : undefined
          }
        >
          <Select
            id={`${uid}-type`}
            disabled={disabled}
            value={params.type}
            onChange={(event) =>
              onChange({ ...params, type: event.target.value, form_prefill: {} })
            }
          >
            <option value="">Select a type…</option>
            {byRecord.enquiry.length > 0 ? (
              <optgroup label="About an enquiry">
                {byRecord.enquiry.map((option) => (
                  <option key={option.slug} value={option.slug}>
                    {option.name}
                  </option>
                ))}
              </optgroup>
            ) : null}
            <optgroup label="About a student">
              {byRecord.student.map((option) => (
                <option key={option.slug} value={option.slug}>
                  {option.name}
                </option>
              ))}
            </optgroup>
          </Select>
        </Field>
        <StrategyField
          id={`${uid}-assign-to`}
          label="Assign to"
          value={params.assign_to}
          options={ASSIGN_TO_STRATEGIES}
          otherLabel="Other (user ID)"
          disabled={disabled}
          onChange={(value) => onChange({ ...params, assign_to: value })}
        />
        <Field
          label="Title"
          htmlFor={`${uid}-title`}
          hint="Leave blank to use the type's own name."
          className="sm:col-span-2"
        >
          <Input
            id={`${uid}-title`}
            disabled={disabled}
            value={params.title ?? ""}
            onChange={(event) => onChange({ ...params, title: event.target.value })}
          />
        </Field>
        <Field label="Notes" htmlFor={`${uid}-summary`} className="sm:col-span-2">
          <Textarea
            id={`${uid}-summary`}
            rows={2}
            disabled={disabled}
            value={params.summary ?? ""}
            onChange={(event) => onChange({ ...params, summary: event.target.value })}
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <NumberField
          id={`${uid}-planned`}
          label="Planned in (hours)"
          value={params.planned_in_hours}
          disabled={disabled}
          onChange={(value) => onChange({ ...params, planned_in_hours: value })}
        />
        <NumberField
          id={`${uid}-due`}
          label="Due in (days)"
          value={params.due_in_days}
          disabled={disabled}
          onChange={(value) => onChange({ ...params, due_in_days: value })}
        />
        <NumberField
          id={`${uid}-due-hours`}
          label="Due in (hours)"
          hint="Added to the days."
          value={params.due_in_hours}
          disabled={disabled}
          onChange={(value) => onChange({ ...params, due_in_hours: value })}
        />
        <Field label="Priority" htmlFor={`${uid}-priority`}>
          <Select
            id={`${uid}-priority`}
            disabled={disabled}
            value={params.priority ?? ""}
            onChange={(event) =>
              onChange({ ...params, priority: event.target.value as ActivityPriority | "" })
            }
          >
            <option value="">Default</option>
            {(Object.keys(ACTIVITY_PRIORITY_LABEL) as ActivityPriority[]).map((value) => (
              <option key={value} value={value}>
                {ACTIVITY_PRIORITY_LABEL[value]}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {formFields.length > 0 ? (
        <fieldset className="space-y-2 rounded-md border border-line p-3">
          <legend className="px-1 text-xs font-medium text-ink">
            Answers filled in ahead (optional)
          </legend>
          <p className="text-2xs text-ink-faint">
            The person completing the activity starts from these and can change them.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {formFields.map((field) => (
              <Field
                key={field.key}
                label={field.label || field.key}
                htmlFor={`${uid}-prefill-${field.key}`}
              >
                {Array.isArray(field.options) && field.options.length > 0 ? (
                  <Select
                    id={`${uid}-prefill-${field.key}`}
                    disabled={disabled}
                    value={prefill[field.key] ?? ""}
                    onChange={(event) => {
                      const next = { ...prefill };
                      if (event.target.value) next[field.key] = event.target.value;
                      else delete next[field.key];
                      onChange({ ...params, form_prefill: next });
                    }}
                  >
                    <option value="">Not filled in</option>
                    {field.options.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label || option.value}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    id={`${uid}-prefill-${field.key}`}
                    disabled={disabled}
                    value={prefill[field.key] ?? ""}
                    placeholder="Not filled in"
                    onChange={(event) => {
                      const next = { ...prefill };
                      if (event.target.value) next[field.key] = event.target.value;
                      else delete next[field.key];
                      onChange({ ...params, form_prefill: next });
                    }}
                  />
                )}
              </Field>
            ))}
          </div>
        </fieldset>
      ) : null}

      <VariableHint variables={variables} />
    </div>
  );
}

/** "Update the enquiry": move it along the pipeline, give it an owner, or
 *  set when to follow up. Anything left as is stays unchanged. */
function UpdateEnquiryFields({
  params,
  onChange,
  disabled,
}: {
  params: UpdateEnquiryActionParams;
  onChange: (next: UpdateEnquiryActionParams) => void;
  disabled: boolean;
}) {
  const uid = useId();
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Stage" htmlFor={`${uid}-stage`}>
        <Select
          id={`${uid}-stage`}
          disabled={disabled}
          value={params.stage ?? ""}
          onChange={(event) =>
            onChange({ ...params, stage: event.target.value as UpdateEnquiryActionParams["stage"] })
          }
        >
          <option value="">Leave as is</option>
          {ENQUIRY_STAGES.map((stage) => (
            <option key={stage} value={stage}>
              {ENQUIRY_STAGE_LABEL[stage]}
            </option>
          ))}
        </Select>
      </Field>
      <StrategyField
        id={`${uid}-owner`}
        label="Owner"
        value={params.owner ?? ""}
        options={[{ value: "", label: "Leave as is" }, ...ENQUIRY_OWNER_STRATEGIES]}
        otherLabel="A specific person (user ID)"
        allowOther={false}
        disabled={disabled}
        onChange={(value) => onChange({ ...params, owner: value })}
      />
      {params.owner ? (
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <Checkbox
            checked={Boolean(params.only_if_unowned)}
            disabled={disabled}
            onCheckedChange={(checked) => onChange({ ...params, only_if_unowned: checked })}
          />
          Only if it has no owner yet
        </label>
      ) : null}
      <NumberField
        id={`${uid}-follow-up`}
        label="Next follow-up in (days)"
        value={params.next_follow_up_in_days}
        disabled={disabled}
        onChange={(value) => onChange({ ...params, next_follow_up_in_days: value })}
      />
      <Field label="Lead quality" htmlFor={`${uid}-quality`}>
        <Select
          id={`${uid}-quality`}
          disabled={disabled}
          value={params.lead_quality ? String(params.lead_quality) : ""}
          onChange={(event) =>
            onChange({
              ...params,
              lead_quality: event.target.value ? Number(event.target.value) : null,
            })
          }
        >
          <option value="">Leave as is</option>
          {[1, 2, 3, 4, 5].map((score) => (
            <option key={score} value={score}>
              {score} of 5
            </option>
          ))}
        </Select>
      </Field>
      {params.stage === "not_interested" || params.stage === "not_eligible" ? (
        <Field label="Lost reason" htmlFor={`${uid}-lost`} className="sm:col-span-2">
          <Input
            id={`${uid}-lost`}
            disabled={disabled}
            value={params.lost_reason ?? ""}
            onChange={(event) => onChange({ ...params, lost_reason: event.target.value })}
          />
        </Field>
      ) : null}
    </div>
  );
}

function SendNotificationFields({
  params,
  onChange,
  disabled,
}: {
  params: SendNotificationActionParams;
  onChange: (next: SendNotificationActionParams) => void;
  disabled: boolean;
}) {
  const uid = useId();
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <StrategyField
        id={`${uid}-to`}
        label="To"
        value={params.to}
        options={[...ROLE_OPTIONS, ...NOTIFICATION_TO_STRATEGIES]}
        otherLabel="Other (user ID)"
        disabled={disabled}
        onChange={(value) => onChange({ ...params, to: value })}
      />
      <Field
        label="Notification kind"
        htmlFor={`${uid}-kind`}
        hint='e.g. "activity.assigned", "risk.changed" — a kind the notification centre recognises.'
      >
        <Input
          id={`${uid}-kind`}
          disabled={disabled}
          value={params.kind}
          onChange={(event) => onChange({ ...params, kind: event.target.value })}
        />
      </Field>
      <Field
        label="Title"
        htmlFor={`${uid}-title`}
        hint="{{student.name}} and other context paths are substituted."
        className="sm:col-span-2"
      >
        <Input
          id={`${uid}-title`}
          disabled={disabled}
          value={params.title ?? ""}
          onChange={(event) => onChange({ ...params, title: event.target.value })}
        />
      </Field>
      <Field label="Body" htmlFor={`${uid}-body`} className="sm:col-span-2">
        <Textarea
          id={`${uid}-body`}
          rows={2}
          disabled={disabled}
          value={params.body ?? ""}
          onChange={(event) => onChange({ ...params, body: event.target.value })}
        />
      </Field>
    </div>
  );
}

function SendTemplateFields({
  params,
  onChange,
  disabled,
  toOtherLabel,
}: {
  params: SendEmailActionParams | SendWhatsappActionParams;
  onChange: (next: SendEmailActionParams | SendWhatsappActionParams) => void;
  disabled: boolean;
  toOtherLabel: string;
}) {
  const uid = useId();
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <StrategyField
        id={`${uid}-to`}
        label="To"
        value={params.to}
        options={[...ROLE_OPTIONS, ...NOTIFICATION_TO_STRATEGIES]}
        otherLabel={toOtherLabel}
        disabled={disabled}
        onChange={(value) => onChange({ ...params, to: value })}
      />
      <Field label="Template key" htmlFor={`${uid}-template`} hint="A published template's key.">
        <Input
          id={`${uid}-template`}
          disabled={disabled}
          value={params.template}
          onChange={(event) => onChange({ ...params, template: event.target.value })}
        />
      </Field>
    </div>
  );
}

function CreateReviewFields({
  params,
  onChange,
  disabled,
}: {
  params: CreateReviewActionParams;
  onChange: (next: CreateReviewActionParams) => void;
  disabled: boolean;
}) {
  const uid = useId();
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Review type" htmlFor={`${uid}-review-type`}>
        <Input
          id={`${uid}-review-type`}
          disabled={disabled}
          value={params.review_type ?? ""}
          placeholder="ad_hoc"
          onChange={(event) => onChange({ ...params, review_type: event.target.value })}
        />
      </Field>
      <StrategyField
        id={`${uid}-reviewer`}
        label="Reviewer"
        value={params.reviewer}
        options={REVIEWER_STRATEGIES}
        otherLabel="Other (user ID)"
        disabled={disabled}
        onChange={(value) => onChange({ ...params, reviewer: value })}
      />
      <Field label="Due in (days)" htmlFor={`${uid}-due`}>
        <Input
          id={`${uid}-due`}
          type="number"
          min={0}
          disabled={disabled}
          value={params.due_in_days ?? ""}
          onChange={(event) =>
            onChange({
              ...params,
              due_in_days: event.target.value === "" ? null : Number(event.target.value),
            })
          }
        />
      </Field>
    </div>
  );
}

function FlagRiskFields({
  params,
  onChange,
  disabled,
}: {
  params: FlagRiskActionParams;
  onChange: (next: FlagRiskActionParams) => void;
  disabled: boolean;
}) {
  const uid = useId();
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Level" htmlFor={`${uid}-level`}>
        <Select
          id={`${uid}-level`}
          disabled={disabled}
          value={params.level}
          onChange={(event) =>
            onChange({ ...params, level: event.target.value as FlagRiskActionParams["level"] })
          }
        >
          <option value="warning">Warning</option>
          <option value="critical">Critical</option>
        </Select>
      </Field>
      <Field label="Reason" htmlFor={`${uid}-reason`} className="sm:col-span-2">
        <Textarea
          id={`${uid}-reason`}
          rows={2}
          disabled={disabled}
          value={params.reason ?? ""}
          onChange={(event) => onChange({ ...params, reason: event.target.value })}
        />
      </Field>
    </div>
  );
}

function ActionRow({
  action,
  activityTypeOptions,
  formOptions,
  variables,
  onChange,
  onRemove,
  disabled,
}: {
  action: AutomationAction;
  activityTypeOptions: ActivityTypeOption[];
  formOptions: { slug: string; name: string }[];
  variables: string[];
  onChange: (next: AutomationAction) => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  const uid = useId();

  return (
    <div className="space-y-4 rounded-md border border-line p-3">
      <div className="flex items-start justify-between gap-3">
        <Field label="Action" htmlFor={`${uid}-action-type`} className="max-w-xs flex-1">
          <Select
            id={`${uid}-action-type`}
            disabled={disabled}
            value={action.type}
            onChange={(event) => onChange(blankActionFor(event.target.value as AutomationActionType))}
          >
            {AUTOMATION_ACTION_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label="Remove action"
          disabled={disabled}
          onClick={onRemove}
        >
          <Trash2 className="size-4" aria-hidden="true" />
        </Button>
      </div>

      {action.type === "create_activity" ? (
        <CreateActivityFields
          params={action.params}
          activityTypeOptions={activityTypeOptions}
          variables={variables}
          disabled={disabled}
          onChange={(params) => onChange({ type: "create_activity", params })}
        />
      ) : action.type === "send_notification" ? (
        <SendNotificationFields
          params={action.params}
          disabled={disabled}
          onChange={(params) => onChange({ type: "send_notification", params })}
        />
      ) : action.type === "send_email" ? (
        <SendTemplateFields
          params={action.params}
          disabled={disabled}
          toOtherLabel="Other (user ID or address)"
          onChange={(params) => onChange({ type: "send_email", params: params as SendEmailActionParams })}
        />
      ) : action.type === "send_whatsapp" ? (
        <SendTemplateFields
          params={action.params}
          disabled={disabled}
          toOtherLabel="Other (user ID or phone)"
          onChange={(params) =>
            onChange({ type: "send_whatsapp", params: params as SendWhatsappActionParams })
          }
        />
      ) : action.type === "create_review" ? (
        <CreateReviewFields
          params={action.params}
          disabled={disabled}
          onChange={(params) => onChange({ type: "create_review", params })}
        />
      ) : action.type === "update_enquiry" ? (
        <UpdateEnquiryFields
          params={action.params}
          disabled={disabled}
          onChange={(params) => onChange({ type: "update_enquiry", params })}
        />
      ) : action.type === "assign_form" ? (
        <AssignFormFields
          params={action.params}
          formOptions={formOptions}
          variables={variables}
          disabled={disabled}
          onChange={(params) => onChange({ type: "assign_form", params })}
        />
      ) : (
        <FlagRiskFields
          params={action.params}
          disabled={disabled}
          onChange={(params) => onChange({ type: "flag_risk", params })}
        />
      )}
    </div>
  );
}

export function ActionEditor({
  actions,
  activityTypeOptions,
  formOptions = [],
  variables = [],
  onChange,
  disabled = false,
}: {
  actions: AutomationAction[];
  activityTypeOptions: ActivityTypeOption[];
  /** Forms an `assign_form` action may send. */
  formOptions?: { slug: string; name: string }[];
  /** `{{path}}` variables the trigger's context offers, for message hints. */
  variables?: string[];
  onChange: (next: AutomationAction[]) => void;
  disabled?: boolean;
}) {
  function update(index: number, next: AutomationAction) {
    const copy = actions.slice();
    copy[index] = next;
    onChange(copy);
  }

  function remove(index: number) {
    onChange(actions.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-3">
      {actions.length === 0 ? (
        <p className="text-sm text-ink-muted">
          No actions yet. A rule with no actions can be tested but never does anything when
          activated.
        </p>
      ) : (
        actions.map((action, index) => (
          <ActionRow
            key={index}
            action={action}
            activityTypeOptions={activityTypeOptions}
            formOptions={formOptions}
            variables={variables}
            disabled={disabled}
            onChange={(next) => update(index, next)}
            onRemove={() => remove(index)}
          />
        ))
      )}
      {!disabled ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange([...actions, blankActionFor("create_activity")])}
        >
          <Plus className="size-4" aria-hidden="true" />
          Add action
        </Button>
      ) : null}
    </div>
  );
}
