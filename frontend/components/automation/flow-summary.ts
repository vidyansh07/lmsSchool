/**
 * One-line, plain-language descriptions of a rule's pieces, for the flow
 * builder's cards ("Counselling call → the enquiry's owner, due in 2 h").
 * Pure functions over the rule's own JSON plus the lookups the builder
 * already loaded, so a card always says what will actually run.
 */

import { allChoices } from "@/components/forms/field-renderer";
import {
  ASSIGN_TO_STRATEGIES,
  ENQUIRY_OWNER_STRATEGIES,
  FORM_RECIPIENT_STRATEGIES,
  NOTIFICATION_TO_STRATEGIES,
  REVIEWER_STRATEGIES,
  operatorTakesNoValue,
} from "@/lib/automation";
import {
  AUTOMATION_OPERATOR_LABEL,
  ENQUIRY_STAGE_LABEL,
  ROLE_OPTIONS,
} from "@/lib/labels";
import type {
  AutomationAction,
  AutomationCondition,
  EnquiryStage,
  FormField,
} from "@/types/api";

export interface SummaryLookups {
  activityTypes: { slug: string; name: string }[];
  forms: { slug: string; name: string }[];
  formFields: FormField[];
}

const STRATEGY_LABEL: Record<string, string> = Object.fromEntries(
  [
    ...ASSIGN_TO_STRATEGIES,
    ...ENQUIRY_OWNER_STRATEGIES,
    ...FORM_RECIPIENT_STRATEGIES,
    ...NOTIFICATION_TO_STRATEGIES,
    ...REVIEWER_STRATEGIES,
    ...ROLE_OPTIONS,
  ].map((option) => [option.value, option.label.charAt(0).toLowerCase() + option.label.slice(1)]),
);

export function strategyLabel(value: string | undefined): string {
  if (!value) return "nobody chosen yet";
  return STRATEGY_LABEL[value] ?? "a specific person";
}

function timing(days?: number | null, hours?: number | null): string {
  const parts: string[] = [];
  if (days) parts.push(`${days} d`);
  if (hours) parts.push(`${hours} h`);
  return parts.length > 0 ? `due in ${parts.join(" ")}` : "";
}

function valueText(condition: AutomationCondition, field: FormField | undefined): string {
  const choices = field ? allChoices(field) : [];
  const label = (value: unknown): string => {
    const text = String(value);
    const option = choices.find((choice) => choice.value === text);
    if (option) return option.label || text;
    if (condition.path.startsWith("enquiry.") && text in ENQUIRY_STAGE_LABEL) {
      return ENQUIRY_STAGE_LABEL[text as EnquiryStage];
    }
    if (value === true) return "yes";
    if (value === false) return "no";
    return text === "" ? "…" : text;
  };
  return Array.isArray(condition.value)
    ? condition.value.map(label).join(", ") || "…"
    : label(condition.value);
}

/** "Lead stage is Not interested", "Remarks is empty". */
export function describeCondition(
  condition: AutomationCondition,
  formFields: FormField[],
): string {
  const field = condition.path.startsWith("form.")
    ? formFields.find((candidate) => `form.${candidate.key}` === condition.path)
    : undefined;
  const subject = field?.label || condition.path || "Something";
  const operator = AUTOMATION_OPERATOR_LABEL[condition.op] ?? condition.op;
  if (operatorTakesNoValue(condition.op)) return `${subject} ${operator}`;
  return `${subject} ${operator} ${valueText(condition, field)}`;
}

function nameOf(list: { slug: string; name: string }[], slug: string | undefined, fallback: string) {
  if (!slug) return fallback;
  return list.find((item) => item.slug === slug)?.name ?? slug;
}

/** "Counselling call → the enquiry's owner, due in 2 h". */
export function describeAction(action: AutomationAction, lookups: SummaryLookups): string {
  switch (action.type) {
    case "create_activity": {
      const params = action.params;
      const what = nameOf(lookups.activityTypes, params.type, "Choose an activity type");
      const when = timing(params.due_in_days, params.due_in_hours);
      return [`${what} → ${strategyLabel(params.assign_to)}`, when].filter(Boolean).join(", ");
    }
    case "update_enquiry": {
      const params = action.params;
      const parts: string[] = [];
      if (params.stage) parts.push(`stage → ${ENQUIRY_STAGE_LABEL[params.stage]}`);
      if (params.owner) {
        parts.push(
          `owner → ${strategyLabel(params.owner)}${params.only_if_unowned ? " if unowned" : ""}`,
        );
      }
      if (params.next_follow_up_in_days) parts.push(`follow up in ${params.next_follow_up_in_days} d`);
      if (params.lead_quality) parts.push(`quality ${params.lead_quality}/5`);
      return parts.length > 0 ? parts.join(", ") : "Choose what to change";
    }
    case "assign_form": {
      const params = action.params;
      const what = nameOf(lookups.forms, params.form, "Choose a form");
      const when = timing(params.due_in_days);
      return [`${what} → ${strategyLabel(params.to)}`, when].filter(Boolean).join(", ");
    }
    case "send_notification":
      return [strategyLabel(action.params.to), action.params.title].filter(Boolean).join(" · ");
    case "send_email":
    case "send_whatsapp":
      return `${strategyLabel(action.params.to)} · template ${action.params.template || "…"}`;
    case "create_review":
      return `Reviewer: ${strategyLabel(action.params.reviewer)}`;
    case "flag_risk":
      return `Mark as ${action.params.level}`;
  }
}
