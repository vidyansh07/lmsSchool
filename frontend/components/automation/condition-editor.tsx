"use client";

/**
 * The condition list editor for one `AutomationRule` (`docs/erp/
 * AUTOMATION_CATALOG.md` "Conditions"). ANDed `{path, op, value}` rows,
 * where `path` is locked to the *selected trigger's* allowlisted context —
 * `AUTOMATION_TRIGGER_PATHS` in `lib/automation.ts` (see that file's module
 * docstring for why this is a constant here rather than a fetched value:
 * there turned out to be no endpoint exposing it).
 *
 * `ACTIVITY_COMPLETED` and `FORM_SUBMITTED` additionally allow any
 * `form.<key>` path. When the builder knows which form the rule is about
 * (`formFields`), each of its questions is offered by label, the operators
 * are narrowed to the ones that make sense for that question's type, and the
 * value is picked the way the question was answered — from its options, as
 * yes/no, or as a number. Without a known form, a row on a form path falls
 * back to a free-text "form field key" input.
 */

import { useId } from "react";
import { Plus, Trash2 } from "lucide-react";

import { allChoices } from "@/components/forms/field-renderer";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import {
  conditionValueToText,
  operatorTakesList,
  operatorTakesNoValue,
  parseConditionList,
  parseConditionLiteral,
  type TriggerPathInfo,
} from "@/lib/automation";
import { AUTOMATION_OPERATOR_LABEL, AUTOMATION_OPERATOR_OPTIONS } from "@/lib/labels";
import type {
  AutomationCondition,
  AutomationConditionOperator,
  FormField,
  FormFieldOption,
  FormFieldType,
} from "@/types/api";

const FORM_PATH_SENTINEL = "__form_field__";

const EMPTINESS: AutomationConditionOperator[] = ["is_empty", "is_not_empty"];

/** The operators that mean something for an answer of this type. */
export function operatorsForFieldType(type: FormFieldType): AutomationConditionOperator[] {
  switch (type) {
    case "number":
    case "decimal":
    case "rating":
      return ["eq", "ne", "lt", "lte", "gt", "gte", ...EMPTINESS];
    case "select":
    case "radio":
    case "dependent_select":
      return ["eq", "ne", "in", "not_in", ...EMPTINESS];
    case "multiselect":
    case "checkbox":
      return ["contains", ...EMPTINESS];
    case "boolean":
    case "consent":
      return ["eq"];
    case "date":
    case "datetime":
    case "time":
      return ["eq", "lt", "gt", ...EMPTINESS];
    default:
      return ["eq", "ne", "contains", ...EMPTINESS];
  }
}

const NUMERIC_TYPES: readonly FormFieldType[] = ["number", "decimal", "rating"];
const CHOICE_TYPES: readonly FormFieldType[] = [
  "select",
  "radio",
  "dependent_select",
  "multiselect",
  "checkbox",
];

function blankCondition(paths: string[]): AutomationCondition {
  return { path: paths[0] ?? "", op: "eq", value: "" };
}

/** The value a condition starts with when its question or operator changes. */
function initialValue(
  field: FormField | undefined,
  op: AutomationConditionOperator,
): AutomationCondition["value"] {
  if (operatorTakesNoValue(op)) return "";
  if (operatorTakesList(op)) return [];
  if (field && (field.type === "boolean" || field.type === "consent")) return true;
  return "";
}

/** The value input for a known form question, typed by how it is answered. */
function FormValueInput({
  id,
  field,
  condition,
  disabled,
  onChange,
}: {
  id: string;
  field: FormField;
  condition: AutomationCondition;
  disabled: boolean;
  onChange: (value: AutomationCondition["value"]) => void;
}) {
  if (field.type === "boolean" || field.type === "consent") {
    return (
      <Select
        id={id}
        disabled={disabled}
        value={condition.value === false ? "false" : "true"}
        onChange={(event) => onChange(event.target.value === "true")}
      >
        <option value="true">Yes</option>
        <option value="false">No</option>
      </Select>
    );
  }
  if (CHOICE_TYPES.includes(field.type)) {
    const choices = allChoices(field);
    return (
      <Select
        id={id}
        disabled={disabled}
        value={typeof condition.value === "string" ? condition.value : String(condition.value)}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Choose…</option>
        {choices.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label || option.value}
          </option>
        ))}
      </Select>
    );
  }
  if (NUMERIC_TYPES.includes(field.type)) {
    return (
      <Input
        id={id}
        type="number"
        disabled={disabled}
        value={typeof condition.value === "number" ? condition.value : ""}
        onChange={(event) =>
          onChange(event.target.value === "" ? "" : Number(event.target.value))
        }
      />
    );
  }
  return (
    <Input
      id={id}
      type={field.type === "date" ? "date" : field.type === "time" ? "time" : "text"}
      disabled={disabled}
      // A text answer compares as text: "123" stays a string here.
      value={typeof condition.value === "string" ? condition.value : String(condition.value ?? "")}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

/** A context path whose answer is one of a fixed list (an enquiry's stage)
 *  is treated like a dropdown question, so it gets the same value picker. */
function choicePathAsField(path: string, choices: FormFieldOption[]): FormField {
  return {
    id: path,
    key: path,
    label: path,
    help: "",
    type: "select",
    required: false,
    order: 0,
    group: "",
    options: choices,
    validation: {},
    visible_to_student: false,
    performance_key: null,
  };
}

function ConditionRow({
  condition,
  triggerMeta,
  formFields,
  choicePaths,
  onChange,
  onRemove,
  disabled,
}: {
  condition: AutomationCondition;
  triggerMeta: TriggerPathInfo;
  formFields: FormField[];
  choicePaths: Record<string, FormFieldOption[]>;
  onChange: (next: AutomationCondition) => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  const uid = useId();
  const answerField = condition.path.startsWith("form.")
    ? formFields.find((field) => `form.${field.key}` === condition.path)
    : undefined;
  const fixedChoices = choicePaths[condition.path];
  // A form question, or a path with a fixed list of answers, gets a typed
  // value picker; every other path keeps the free-text value.
  const formField =
    answerField ?? (fixedChoices ? choicePathAsField(condition.path, fixedChoices) : undefined);
  const isKnownPath = triggerMeta.paths.includes(condition.path) || Boolean(answerField);
  const isFormPath =
    !isKnownPath && triggerMeta.allowsFormPaths && condition.path.startsWith("form.");
  const isUnrecognisedPath = !isKnownPath && !isFormPath && condition.path !== "";
  const isList = operatorTakesList(condition.op);
  const takesValue = !operatorTakesNoValue(condition.op);
  const choices = formField ? allChoices(formField) : [];
  const pickListFromChoices = Boolean(formField) && isList && choices.length > 0;
  const listValue = Array.isArray(condition.value) ? condition.value.map(String) : [];

  const operators = formField
    ? operatorsForFieldType(formField.type)
    : AUTOMATION_OPERATOR_OPTIONS.map((option) => option.value);
  // Keep an operator already on the rule selectable even if this question's
  // type would not offer it, so loading a rule never silently rewrites it.
  const operatorChoices = operators.includes(condition.op)
    ? operators
    : [condition.op, ...operators];

  function changePath(path: string) {
    const nextField = path.startsWith("form.")
      ? formFields.find((field) => `form.${field.key}` === path)
      : choicePaths[path]
        ? choicePathAsField(path, choicePaths[path])
        : undefined;
    if (!nextField) {
      onChange({ ...condition, path });
      return;
    }
    const allowed = operatorsForFieldType(nextField.type);
    const op = allowed.includes(condition.op) ? condition.op : (allowed[0] ?? "eq");
    onChange({ path, op, value: initialValue(nextField, op) });
  }

  return (
    <div className="grid grid-cols-1 gap-2 rounded-md border border-line p-3 sm:grid-cols-[1fr_auto]">
      <div className="space-y-2">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Field label="When" htmlFor={`${uid}-path`}>
            {isFormPath ? (
              <Input
                id={`${uid}-path`}
                value={condition.path.slice("form.".length)}
                placeholder="form field key"
                disabled={disabled}
                onChange={(event) =>
                  onChange({ ...condition, path: `form.${event.target.value.trim()}` })
                }
              />
            ) : (
              <Select
                id={`${uid}-path`}
                disabled={disabled}
                value={isUnrecognisedPath || isKnownPath ? condition.path : FORM_PATH_SENTINEL}
                onChange={(event) => {
                  const value = event.target.value;
                  changePath(value === FORM_PATH_SENTINEL ? "form." : value);
                }}
              >
                {isUnrecognisedPath ? (
                  <option value={condition.path}>{condition.path} (no longer allowed)</option>
                ) : null}
                {formFields.length > 0 ? (
                  <optgroup label="Form answers">
                    {formFields.map((field) => (
                      <option key={field.key} value={`form.${field.key}`}>
                        {field.label || field.key}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
                <optgroup label={formFields.length > 0 ? "About the event" : "Context"}>
                  {triggerMeta.paths.map((path) => (
                    <option key={path} value={path}>
                      {path}
                    </option>
                  ))}
                </optgroup>
                {triggerMeta.allowsFormPaths ? (
                  <option value={FORM_PATH_SENTINEL}>Another form field (by key)…</option>
                ) : null}
              </Select>
            )}
          </Field>
          <Field label="Operator" htmlFor={`${uid}-op`}>
            <Select
              id={`${uid}-op`}
              disabled={disabled}
              value={condition.op}
              onChange={(event) => {
                const op = event.target.value as AutomationConditionOperator;
                // Switching to/from a list or a no-value operator needs the
                // value re-shaped, not just re-typed against the old one.
                let value: AutomationCondition["value"] = condition.value;
                if (operatorTakesNoValue(op)) value = "";
                else if (operatorTakesList(op)) value = Array.isArray(value) ? value : [];
                else if (Array.isArray(value) || operatorTakesNoValue(condition.op)) {
                  value = initialValue(formField, op);
                }
                onChange({ ...condition, op, value });
              }}
            >
              {operatorChoices.map((op) => (
                <option key={op} value={op}>
                  {AUTOMATION_OPERATOR_LABEL[op]}
                </option>
              ))}
            </Select>
          </Field>
          {takesValue && !pickListFromChoices ? (
            <Field
              label="Value"
              htmlFor={`${uid}-value`}
              hint={isList ? "Comma-separated" : undefined}
            >
              {formField && !isList ? (
                <FormValueInput
                  id={`${uid}-value`}
                  field={formField}
                  condition={condition}
                  disabled={disabled}
                  onChange={(value) => onChange({ ...condition, value })}
                />
              ) : (
                <Input
                  id={`${uid}-value`}
                  disabled={disabled}
                  value={conditionValueToText(condition.value)}
                  onChange={(event) =>
                    onChange({
                      ...condition,
                      value: isList
                        ? parseConditionList(event.target.value)
                        : parseConditionLiteral(event.target.value),
                    })
                  }
                />
              )}
            </Field>
          ) : null}
        </div>
        {takesValue && pickListFromChoices && formField ? (
          <div
            className="flex flex-wrap gap-x-4 gap-y-2"
            role="group"
            aria-label={`${formField.label || formField.key} answers`}
          >
            {choices.map((option) => (
              <label key={option.value} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={listValue.includes(option.value)}
                  disabled={disabled}
                  onCheckedChange={(checked) => {
                    const next = new Set(listValue);
                    if (checked) next.add(option.value);
                    else next.delete(option.value);
                    onChange({ ...condition, value: Array.from(next) });
                  }}
                />
                {option.label || option.value}
              </label>
            ))}
          </div>
        ) : null}
      </div>
      <div className="flex items-start justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label="Remove condition"
          disabled={disabled}
          onClick={onRemove}
        >
          <Trash2 className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

export function ConditionEditor({
  conditions,
  triggerMeta,
  triggerLabel,
  formFields = [],
  choicePaths = {},
  onChange,
  disabled = false,
}: {
  conditions: AutomationCondition[];
  triggerMeta: TriggerPathInfo;
  /** For the empty-state sentence only — the trigger's own friendly name. */
  triggerLabel: string;
  /** The questions of the form this rule is about, when known — offered as
   *  `form.<key>` conditions. Headings are left out by the caller. */
  formFields?: FormField[];
  /** Context paths whose answer is one of a fixed list, e.g. an enquiry's
   *  stage — offered as a dropdown value instead of free text. */
  choicePaths?: Record<string, FormFieldOption[]>;
  onChange: (next: AutomationCondition[]) => void;
  disabled?: boolean;
}) {
  function update(index: number, next: AutomationCondition) {
    const copy = conditions.slice();
    copy[index] = next;
    onChange(copy);
  }

  function remove(index: number) {
    onChange(conditions.filter((_, i) => i !== index));
  }

  function add() {
    const [first] = formFields;
    if (first) {
      const op = operatorsForFieldType(first.type)[0] ?? "eq";
      onChange([...conditions, { path: `form.${first.key}`, op, value: initialValue(first, op) }]);
    } else {
      onChange([...conditions, blankCondition(triggerMeta.paths)]);
    }
  }

  return (
    <div className="space-y-3">
      {conditions.length === 0 ? (
        <p className="text-sm text-ink-muted">
          No conditions — this rule fires on every occurrence of &ldquo;
          {triggerLabel}&rdquo;.
        </p>
      ) : (
        conditions.map((condition, index) => (
          <ConditionRow
            key={index}
            condition={condition}
            triggerMeta={triggerMeta}
            formFields={formFields}
            choicePaths={choicePaths}
            disabled={disabled}
            onChange={(next) => update(index, next)}
            onRemove={() => remove(index)}
          />
        ))
      )}
      {!disabled ? (
        <Button type="button" variant="outline" size="sm" onClick={add}>
          <Plus className="size-4" aria-hidden="true" />
          Add condition
        </Button>
      ) : null}
    </div>
  );
}
