"use client";

/**
 * The condition list editor for one `AutomationRule` (`docs/erp/
 * AUTOMATION_CATALOG.md` "Conditions"). ANDed `{path, op, value}` rows,
 * where `path` is locked to the *selected trigger's* allowlisted context —
 * `AUTOMATION_TRIGGER_PATHS` in `lib/automation.ts` (see that file's module
 * docstring for why this is a constant here rather than a fetched value:
 * there turned out to be no endpoint exposing it).
 *
 * `ACTIVITY_COMPLETED` additionally allows any `form.<key>` path (the pinned
 * form varies by activity type, so there is no fixed list); a row on that
 * path switches to a free-text "form field key" input instead of the select.
 */

import { useId } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import {
  conditionValueToText,
  operatorTakesList,
  parseConditionList,
  parseConditionLiteral,
  type TriggerPathInfo,
} from "@/lib/automation";
import { AUTOMATION_OPERATOR_OPTIONS } from "@/lib/labels";
import type { AutomationCondition } from "@/types/api";

const FORM_PATH_SENTINEL = "__form_field__";

function blankCondition(paths: string[]): AutomationCondition {
  return { path: paths[0] ?? "", op: "eq", value: "" };
}

function ConditionRow({
  condition,
  triggerMeta,
  onChange,
  onRemove,
  disabled,
}: {
  condition: AutomationCondition;
  triggerMeta: TriggerPathInfo;
  onChange: (next: AutomationCondition) => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  const uid = useId();
  const isKnownPath = triggerMeta.paths.includes(condition.path);
  const isFormPath =
    !isKnownPath && triggerMeta.allowsFormPaths && condition.path.startsWith("form.");
  const isUnrecognisedPath = !isKnownPath && !isFormPath && condition.path !== "";
  const isList = operatorTakesList(condition.op);

  return (
    <div className="grid grid-cols-1 gap-2 rounded-md border border-line p-3 sm:grid-cols-[1fr_auto]">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Field label="Path" htmlFor={`${uid}-path`}>
          {isFormPath ? (
            <Input
              id={`${uid}-path`}
              value={condition.path.slice("form.".length)}
              placeholder="field key"
              disabled={disabled}
              onChange={(event) =>
                onChange({ ...condition, path: `form.${event.target.value.trim()}` })
              }
            />
          ) : (
            <Select
              id={`${uid}-path`}
              disabled={disabled}
              value={
                isUnrecognisedPath
                  ? condition.path
                  : isKnownPath
                    ? condition.path
                    : FORM_PATH_SENTINEL
              }
              onChange={(event) => {
                const value = event.target.value;
                onChange({ ...condition, path: value === FORM_PATH_SENTINEL ? "form." : value });
              }}
            >
              {isUnrecognisedPath ? (
                <option value={condition.path}>{condition.path} (no longer allowed)</option>
              ) : null}
              {triggerMeta.paths.map((path) => (
                <option key={path} value={path}>
                  {path}
                </option>
              ))}
              {triggerMeta.allowsFormPaths ? (
                <option value={FORM_PATH_SENTINEL}>Custom form field…</option>
              ) : null}
            </Select>
          )}
        </Field>
        <Field label="Operator" htmlFor={`${uid}-op`}>
          <Select
            id={`${uid}-op`}
            disabled={disabled}
            value={condition.op}
            onChange={(event) =>
              onChange({
                ...condition,
                op: event.target.value as AutomationCondition["op"],
                // Switching to/from a list operator needs the value
                // re-shaped, not just re-typed against the old one.
                value: operatorTakesList(event.target.value as AutomationCondition["op"])
                  ? Array.isArray(condition.value)
                    ? condition.value
                    : []
                  : Array.isArray(condition.value)
                    ? ""
                    : condition.value,
              })
            }
          >
            {AUTOMATION_OPERATOR_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Value"
          htmlFor={`${uid}-value`}
          hint={isList ? "Comma-separated" : undefined}
        >
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
        </Field>
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
  onChange,
  disabled = false,
}: {
  conditions: AutomationCondition[];
  triggerMeta: TriggerPathInfo;
  /** For the empty-state sentence only — the trigger's own friendly name. */
  triggerLabel: string;
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
          onClick={() => onChange([...conditions, blankCondition(triggerMeta.paths)])}
        >
          <Plus className="size-4" aria-hidden="true" />
          Add condition
        </Button>
      ) : null}
    </div>
  );
}
