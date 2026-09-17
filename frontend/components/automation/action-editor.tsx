"use client";

/**
 * The action list editor for one `AutomationRule` (`docs/erp/
 * AUTOMATION_CATALOG.md` "Actions"). Each of the six action types has its
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
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import {
  ASSIGN_TO_STRATEGIES,
  NOTIFICATION_TO_STRATEGIES,
  REVIEWER_STRATEGIES,
} from "@/lib/automation";
import { ACTIVITY_PRIORITY_LABEL, AUTOMATION_ACTION_TYPE_OPTIONS, ROLE_OPTIONS } from "@/lib/labels";
import type {
  ActivityPriority,
  AutomationAction,
  AutomationActionType,
  CreateActivityActionParams,
  CreateReviewActionParams,
  FlagRiskActionParams,
  SendEmailActionParams,
  SendNotificationActionParams,
  SendWhatsappActionParams,
} from "@/types/api";

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
}: {
  id: string;
  label: string;
  hint?: string;
  value: string;
  options: { value: string; label: string }[];
  otherLabel: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const isKnown = options.some((option) => option.value === value);
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
          <option value={OTHER_STRATEGY}>{otherLabel}</option>
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
  }
}

function CreateActivityFields({
  params,
  activityTypeOptions,
  onChange,
  disabled,
}: {
  params: CreateActivityActionParams;
  activityTypeOptions: { slug: string; name: string }[];
  onChange: (next: CreateActivityActionParams) => void;
  disabled: boolean;
}) {
  const uid = useId();
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Activity type" htmlFor={`${uid}-type`}>
        <Select
          id={`${uid}-type`}
          disabled={disabled}
          value={params.type}
          onChange={(event) => onChange({ ...params, type: event.target.value })}
        >
          <option value="">Select a type…</option>
          {activityTypeOptions.map((option) => (
            <option key={option.slug} value={option.slug}>
              {option.name}
            </option>
          ))}
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
      <Field label="Priority" htmlFor={`${uid}-priority`} hint="Leave unset for the type's own default.">
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
      <Field label="Title" htmlFor={`${uid}-title`} hint="Leave blank to use the type's own name." className="sm:col-span-2">
        <Input
          id={`${uid}-title`}
          disabled={disabled}
          value={params.title ?? ""}
          onChange={(event) => onChange({ ...params, title: event.target.value })}
        />
      </Field>
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
  onChange,
  onRemove,
  disabled,
}: {
  action: AutomationAction;
  activityTypeOptions: { slug: string; name: string }[];
  onChange: (next: AutomationAction) => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  const uid = useId();

  return (
    <div className="space-y-4 rounded-md border border-border p-3">
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
  onChange,
  disabled = false,
}: {
  actions: AutomationAction[];
  activityTypeOptions: { slug: string; name: string }[];
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
        <p className="text-sm text-muted-foreground">
          No actions yet. A rule with no actions can be tested but never does anything when
          activated.
        </p>
      ) : (
        actions.map((action, index) => (
          <ActionRow
            key={index}
            action={action}
            activityTypeOptions={activityTypeOptions}
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
