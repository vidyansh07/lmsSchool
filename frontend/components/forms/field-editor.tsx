"use client";

/**
 * The field list editor for a draft `FormVersion`.
 *
 * Local state only — nothing is written until the caller's "Save" persists
 * the whole list with `PUT .../fields/` (a full replace; the server 409s if
 * the version is no longer a draft). Reordering renumbers `order` on every
 * field so it always matches the array's own position, which is also what
 * the preview panel and `FieldRenderer` sort by.
 */

import { useId, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Plus,
  Trash2,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import {
  FieldRenderer,
  allChoices,
  relationModel,
  valuesForSubmit,
  type FormValues,
} from "@/components/forms/field-renderer";
import { fieldErrors } from "@/lib/api";
import { FORM_FIELD_CHOICE_TYPES, FORM_FIELD_TYPE_OPTIONS } from "@/lib/labels";
import { previewForm } from "@/lib/forms";
import type {
  FormFieldDependentOptions,
  FormFieldInput,
  FormFieldOption,
  FormFieldRelationModel,
  FormFieldShowIf,
  FormFieldType,
  FormShowIfOperator,
} from "@/types/api";

/** Types a dependent dropdown may hang off. */
const PARENT_TYPES: readonly FormFieldType[] = ["select", "radio", "dependent_select"];

const SHOW_IF_OPERATORS: { value: FormShowIfOperator; label: string }[] = [
  { value: "eq", label: "is" },
  { value: "ne", label: "is not" },
  { value: "in", label: "is one of" },
  { value: "not_in", label: "is none of" },
  { value: "filled", label: "is filled in" },
  { value: "empty", label: "is empty" },
];

function dependentOptionsOf(field: FormFieldInput): FormFieldDependentOptions {
  const options = field.options;
  if (options && !Array.isArray(options) && "parent" in options) return options;
  return { parent: "", choices: {} };
}

const RELATION_MODELS: FormFieldRelationModel[] = ["student", "trainer", "batch"];

let localIdSeq = 0;
function localId(): string {
  localIdSeq += 1;
  return `new-${localIdSeq}`;
}

function blankField(order: number): FormFieldInput {
  return {
    key: "",
    label: "",
    help: "",
    type: "text",
    required: false,
    order,
    group: "",
    options: null,
    validation: {},
    visible_to_student: false,
    performance_key: null,
    show_if: {},
  };
}

function withOrders(fields: FormFieldInput[]): FormFieldInput[] {
  return fields.map((field, index) => ({ ...field, order: index }));
}

/** Choice-list editor for `select`/`multiselect`/`radio`/`checkbox`. */
function OptionsEditor({
  options,
  onChange,
}: {
  options: FormFieldOption[];
  onChange: (next: FormFieldOption[]) => void;
}) {
  return (
    <div className="space-y-2">
      {options.map((option, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            aria-label={`Option ${index + 1} value`}
            placeholder="value"
            value={option.value}
            onChange={(event) => {
              const next = options.slice();
              next[index] = { ...option, value: event.target.value };
              onChange(next);
            }}
          />
          <Input
            aria-label={`Option ${index + 1} label`}
            placeholder="label"
            value={option.label}
            onChange={(event) => {
              const next = options.slice();
              next[index] = { ...option, label: event.target.value };
              onChange(next);
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={`Remove option ${index + 1}`}
            onClick={() => onChange(options.filter((_, i) => i !== index))}
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange([...options, { value: "", label: "" }])}
      >
        <Plus className="size-4" aria-hidden="true" />
        Add option
      </Button>
    </div>
  );
}

/** The validation keys relevant to a given field type
 *  (`FORM_CATALOG.md` "Validation rules"). */
function validationKeysFor(type: FormFieldType): string[] {
  switch (type) {
    case "text":
    case "textarea":
    case "richtext":
      return ["min_length", "max_length", "pattern"];
    case "number":
    case "decimal":
      return ["min", "max"];
    case "multiselect":
    case "checkbox":
      return ["min_items", "max_items"];
    case "file":
    case "image":
      return ["accept", "max_mb"];
    case "rating":
      return ["max"];
    case "time":
      return ["min_time", "max_time"];
    case "hidden":
      return ["default"];
    default:
      return [];
  }
}

/** "Show only when" — another, earlier field's answer this one depends on. */
function ShowIfEditor({
  uid,
  field,
  earlier,
  onChange,
}: {
  uid: string;
  field: FormFieldInput;
  earlier: FormFieldInput[];
  onChange: (next: FormFieldShowIf) => void;
}) {
  const rule = field.show_if ?? {};
  const candidates = earlier.filter((other) => other.key && other.type !== "heading");
  const parent = candidates.find((other) => other.key === rule.field);
  const op = rule.op ?? "eq";
  const needsValue = op !== "filled" && op !== "empty";
  const choices = parent ? allChoices(parent) : [];
  const isBoolean = parent?.type === "boolean" || parent?.type === "consent";
  const isList = op === "in" || op === "not_in";
  const listValue = Array.isArray(rule.value) ? rule.value.map(String) : [];

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="Show only when" htmlFor={`${uid}-show-if-field`} hint="Leave as Always to show it every time.">
          <Select
            id={`${uid}-show-if-field`}
            value={rule.field ?? ""}
            onChange={(event) =>
              onChange(event.target.value ? { field: event.target.value, op: "eq", value: "" } : {})
            }
          >
            <option value="">Always</option>
            {candidates.map((other) => (
              <option key={other.key} value={other.key}>
                {other.label || other.key}
              </option>
            ))}
          </Select>
        </Field>
        {rule.field ? (
          <Field label="Condition" htmlFor={`${uid}-show-if-op`}>
            <Select
              id={`${uid}-show-if-op`}
              value={op}
              onChange={(event) => {
                const nextOp = event.target.value as FormShowIfOperator;
                const nextValue =
                  nextOp === "in" || nextOp === "not_in"
                    ? []
                    : nextOp === "filled" || nextOp === "empty"
                      ? undefined
                      : isBoolean
                        ? true
                        : "";
                onChange({ field: rule.field, op: nextOp, value: nextValue });
              }}
            >
              {SHOW_IF_OPERATORS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        {rule.field && needsValue && !isList ? (
          <Field label="Answer" htmlFor={`${uid}-show-if-value`}>
            {isBoolean ? (
              <Select
                id={`${uid}-show-if-value`}
                value={rule.value === true ? "true" : rule.value === false ? "false" : ""}
                onChange={(event) =>
                  onChange({ ...rule, value: event.target.value === "true" })
                }
              >
                <option value="true">Yes</option>
                <option value="false">No</option>
              </Select>
            ) : choices.length > 0 ? (
              <Select
                id={`${uid}-show-if-value`}
                value={typeof rule.value === "string" ? rule.value : ""}
                onChange={(event) => onChange({ ...rule, value: event.target.value })}
              >
                <option value="">Choose…</option>
                {choices.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label || option.value}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                id={`${uid}-show-if-value`}
                value={rule.value === undefined ? "" : String(rule.value)}
                onChange={(event) => onChange({ ...rule, value: event.target.value })}
              />
            )}
          </Field>
        ) : null}
      </div>
      {rule.field && isList ? (
        <div className="flex flex-wrap gap-x-4 gap-y-2" role="group" aria-label="Answers">
          {choices.length === 0 ? (
            <p className="text-2xs text-ink-faint">
              The field this depends on has no options to pick from.
            </p>
          ) : (
            choices.map((option) => (
              <label key={option.value} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={listValue.includes(option.value)}
                  onCheckedChange={(checked) => {
                    const next = new Set(listValue);
                    if (checked) next.add(option.value);
                    else next.delete(option.value);
                    onChange({ ...rule, value: Array.from(next) });
                  }}
                />
                {option.label || option.value}
              </label>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}

/** A dependent dropdown's settings: which earlier field it follows, and the
 *  choices offered for each of that field's answers. */
function DependentChoicesEditor({
  uid,
  field,
  earlier,
  onChange,
}: {
  uid: string;
  field: FormFieldInput;
  earlier: FormFieldInput[];
  onChange: (next: FormFieldDependentOptions) => void;
}) {
  const options = dependentOptionsOf(field);
  const parents = earlier.filter((other) => other.key && PARENT_TYPES.includes(other.type));
  const parent = parents.find((other) => other.key === options.parent);
  const parentAnswers = parent ? allChoices(parent) : [];

  return (
    <div className="space-y-3">
      <Field
        label="Depends on"
        htmlFor={`${uid}-dependent-parent`}
        hint="A dropdown or radio field above this one."
      >
        <Select
          id={`${uid}-dependent-parent`}
          value={options.parent}
          onChange={(event) => onChange({ parent: event.target.value, choices: {} })}
        >
          <option value="">Choose a field…</option>
          {parents.map((other) => (
            <option key={other.key} value={other.key}>
              {other.label || other.key}
            </option>
          ))}
        </Select>
      </Field>
      {parent && parentAnswers.length === 0 ? (
        <p className="text-2xs text-ink-faint">Add options to that field first.</p>
      ) : null}
      {parentAnswers.map((answer) => (
        <div key={answer.value} className="space-y-1.5 rounded-control border border-line p-3">
          <p className="text-xs font-medium text-ink">
            When “{answer.label || answer.value}” is chosen, offer:
          </p>
          <OptionsEditor
            options={options.choices[answer.value] ?? []}
            onChange={(next) =>
              onChange({ ...options, choices: { ...options.choices, [answer.value]: next } })
            }
          />
        </div>
      ))}
    </div>
  );
}

function FieldRow({
  field,
  index,
  total,
  earlier,
  onChange,
  onRemove,
  onMove,
}: {
  field: FormFieldInput;
  index: number;
  total: number;
  /** The fields above this one — the only ones it may depend on. */
  earlier: FormFieldInput[];
  onChange: (next: FormFieldInput) => void;
  onRemove: () => void;
  onMove: (direction: -1 | 1) => void;
}) {
  const uid = useId();
  const validationKeys = validationKeysFor(field.type);
  const isChoiceType = FORM_FIELD_CHOICE_TYPES.includes(field.type);
  const isHeading = field.type === "heading";

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <CardTitle className="text-base">
          {field.label || field.key || "Untitled field"}
        </CardTitle>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Move field up"
            disabled={index === 0}
            onClick={() => onMove(-1)}
          >
            <ChevronUp className="size-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Move field down"
            disabled={index === total - 1}
            onClick={() => onMove(1)}
          >
            <ChevronDown className="size-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={`Remove field ${field.label || field.key}`}
            onClick={onRemove}
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Key" htmlFor={`${uid}-key`} hint="snake_case, unique on this version">
            <Input
              id={`${uid}-key`}
              value={field.key}
              onChange={(event) => onChange({ ...field, key: event.target.value })}
            />
          </Field>
          <Field label="Label" htmlFor={`${uid}-label`}>
            <Input
              id={`${uid}-label`}
              value={field.label}
              onChange={(event) => onChange({ ...field, label: event.target.value })}
            />
          </Field>
          <Field label="Type" htmlFor={`${uid}-type`}>
            <Select
              id={`${uid}-type`}
              value={field.type}
              onChange={(event) => {
                const type = event.target.value as FormFieldType;
                const nextIsChoice = FORM_FIELD_CHOICE_TYPES.includes(type);
                onChange({
                  ...field,
                  type,
                  options: nextIsChoice
                    ? []
                    : type === "relation"
                      ? { model: "student" }
                      : type === "dependent_select"
                        ? { parent: "", choices: {} }
                        : null,
                  validation: type === "rating" ? { max: 5 } : {},
                  required: type === "heading" ? false : type === "consent" ? true : field.required,
                });
              }}
            >
              {FORM_FIELD_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Group" htmlFor={`${uid}-group`} hint="Optional section heading">
            <Input
              id={`${uid}-group`}
              value={field.group}
              onChange={(event) => onChange({ ...field, group: event.target.value })}
            />
          </Field>
        </div>

        <Field label="Help text" htmlFor={`${uid}-help`}>
          <Textarea
            id={`${uid}-help`}
            rows={2}
            value={field.help}
            onChange={(event) => onChange({ ...field, help: event.target.value })}
          />
        </Field>

        <div className="flex flex-wrap gap-6">
          {!isHeading ? (
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={field.required}
                onCheckedChange={(checked) => onChange({ ...field, required: checked })}
              />
              Required
            </label>
          ) : null}
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={field.visible_to_student}
              onCheckedChange={(checked) =>
                onChange({ ...field, visible_to_student: checked })
              }
            />
            Visible to student
          </label>
        </div>

        {!isHeading ? (
        <Field
          label="Performance key"
          htmlFor={`${uid}-performance-key`}
          hint='Set to "score" (or another key) to feed the activity score; leave blank otherwise.'
        >
          <Input
            id={`${uid}-performance-key`}
            value={field.performance_key ?? ""}
            onChange={(event) =>
              onChange({
                ...field,
                performance_key: event.target.value.trim() || null,
              })
            }
          />
        </Field>
        ) : null}

        <ShowIfEditor
          uid={uid}
          field={field}
          earlier={earlier}
          onChange={(show_if) => onChange({ ...field, show_if })}
        />

        {field.type === "relation" ? (
          <Field label="Related model" htmlFor={`${uid}-relation-model`}>
            <Select
              id={`${uid}-relation-model`}
              value={relationModel(field.options) ?? "student"}
              onChange={(event) =>
                onChange({
                  ...field,
                  options: {
                    model: event.target.value as FormFieldRelationModel,
                  },
                })
              }
            >
              {RELATION_MODELS.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}

        {field.type === "dependent_select" ? (
          <DependentChoicesEditor
            uid={uid}
            field={field}
            earlier={earlier}
            onChange={(options) => onChange({ ...field, options })}
          />
        ) : null}

        {isChoiceType ? (
          <Field label="Options" htmlFor={`${uid}-options`}>
            <OptionsEditor
              options={Array.isArray(field.options) ? field.options : []}
              onChange={(options) => onChange({ ...field, options })}
            />
          </Field>
        ) : null}

        {validationKeys.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {validationKeys.includes("min_length") ? (
              <Field label="Min length" htmlFor={`${uid}-min-length`}>
                <Input
                  id={`${uid}-min-length`}
                  type="number"
                  value={field.validation.min_length ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: {
                        ...field.validation,
                        min_length: event.target.value
                          ? Number(event.target.value)
                          : undefined,
                      },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("max_length") ? (
              <Field label="Max length" htmlFor={`${uid}-max-length`}>
                <Input
                  id={`${uid}-max-length`}
                  type="number"
                  value={field.validation.max_length ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: {
                        ...field.validation,
                        max_length: event.target.value
                          ? Number(event.target.value)
                          : undefined,
                      },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("pattern") ? (
              <Field label="Pattern" htmlFor={`${uid}-pattern`} hint="Regular expression">
                <Input
                  id={`${uid}-pattern`}
                  value={field.validation.pattern ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: {
                        ...field.validation,
                        pattern: event.target.value || undefined,
                      },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("min") ? (
              <Field label="Min" htmlFor={`${uid}-min`}>
                <Input
                  id={`${uid}-min`}
                  type="number"
                  value={field.validation.min ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: {
                        ...field.validation,
                        min: event.target.value
                          ? Number(event.target.value)
                          : undefined,
                      },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("max") ? (
              <Field label={field.type === "rating" ? "Number of stars" : "Max"} htmlFor={`${uid}-max`}>
                <Input
                  id={`${uid}-max`}
                  type="number"
                  value={field.validation.max ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: {
                        ...field.validation,
                        max: event.target.value
                          ? Number(event.target.value)
                          : undefined,
                      },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("min_time") ? (
              <Field label="Earliest time" htmlFor={`${uid}-min-time`}>
                <Input
                  id={`${uid}-min-time`}
                  type="time"
                  value={typeof field.validation.min === "string" ? field.validation.min : ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: { ...field.validation, min: event.target.value || undefined },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("max_time") ? (
              <Field label="Latest time" htmlFor={`${uid}-max-time`}>
                <Input
                  id={`${uid}-max-time`}
                  type="time"
                  value={typeof field.validation.max === "string" ? field.validation.max : ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: { ...field.validation, max: event.target.value || undefined },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("default") ? (
              <Field
                label="Default value"
                htmlFor={`${uid}-default`}
                hint="Stored when the form sends nothing, e.g. walk-in."
              >
                <Input
                  id={`${uid}-default`}
                  value={field.validation.default ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: { ...field.validation, default: event.target.value || undefined },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("min_items") ? (
              <Field label="Min selections" htmlFor={`${uid}-min-items`}>
                <Input
                  id={`${uid}-min-items`}
                  type="number"
                  value={field.validation.min_items ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: {
                        ...field.validation,
                        min_items: event.target.value
                          ? Number(event.target.value)
                          : undefined,
                      },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("max_items") ? (
              <Field label="Max selections" htmlFor={`${uid}-max-items`}>
                <Input
                  id={`${uid}-max-items`}
                  type="number"
                  value={field.validation.max_items ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: {
                        ...field.validation,
                        max_items: event.target.value
                          ? Number(event.target.value)
                          : undefined,
                      },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("accept") ? (
              <Field
                label="Accepted types"
                htmlFor={`${uid}-accept`}
                hint="Comma-separated, e.g. .pdf,.docx"
              >
                <Input
                  id={`${uid}-accept`}
                  value={(field.validation.accept ?? []).join(",")}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: {
                        ...field.validation,
                        accept: event.target.value
                          ? event.target.value.split(",").map((entry) => entry.trim())
                          : undefined,
                      },
                    })
                  }
                />
              </Field>
            ) : null}
            {validationKeys.includes("max_mb") ? (
              <Field label="Max size (MB)" htmlFor={`${uid}-max-mb`}>
                <Input
                  id={`${uid}-max-mb`}
                  type="number"
                  value={field.validation.max_mb ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...field,
                      validation: {
                        ...field.validation,
                        max_mb: event.target.value
                          ? Number(event.target.value)
                          : undefined,
                      },
                    })
                  }
                />
              </Field>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/**
 * Add/remove/reorder editor plus a "Preview" panel that posts sample values
 * to `POST /forms/{slug}/preview/` and shows the field-level errors inline.
 */
export function FieldEditor({
  slug,
  fields,
  onChange,
  disabled = false,
}: {
  /** The owning definition's slug — needed only for the preview call. */
  slug: string;
  fields: FormFieldInput[];
  onChange: (fields: FormFieldInput[]) => void;
  /** True once the version is published: the fields render read-only and
   *  "Add field" is hidden, matching the 409-on-write server rule. */
  disabled?: boolean;
}) {
  const [previewValues, setPreviewValues] = useState<FormValues>({});
  const [previewErrors, setPreviewErrors] = useState<Record<string, string>>({});
  const [previewNotice, setPreviewNotice] = useState<string | null>(null);
  const [previewFailure, setPreviewFailure] = useState<string | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const sorted = fields.slice().sort((a, b) => a.order - b.order);

  function updateAt(index: number, next: FormFieldInput) {
    const copy = fields.slice();
    copy[index] = next;
    onChange(copy);
  }

  function removeAt(index: number) {
    onChange(withOrders(fields.filter((_, i) => i !== index)));
  }

  function moveAt(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= fields.length) return;
    const copy = fields.slice();
    const moved = copy.splice(index, 1)[0];
    if (!moved) return;
    copy.splice(target, 0, moved);
    onChange(withOrders(copy));
  }

  function addField() {
    onChange(withOrders([...fields, { ...blankField(fields.length), id: localId() }]));
  }

  async function runPreview() {
    setIsPreviewing(true);
    setPreviewNotice(null);
    setPreviewFailure(null);
    setPreviewErrors({});
    try {
      const shaped = sorted
        .filter((field) => field.key)
        .map((field) => ({ ...field, id: field.id ?? field.key }));
      const result = await previewForm(slug, valuesForSubmit(shaped, previewValues));
      const flattened: Record<string, string> = {};
      for (const [key, messages] of Object.entries(result.errors)) {
        const [first] = messages;
        if (first) flattened[key] = first;
      }
      setPreviewErrors(flattened);
      setPreviewNotice(
        Object.keys(flattened).length === 0
          ? "These values pass validation."
          : null,
      );
    } catch (cause) {
      const mapped = fieldErrors(cause);
      const { __all__, ...rest } = mapped;
      setPreviewErrors(rest);
      setPreviewFailure(__all__ ?? "The preview values did not validate.");
    } finally {
      setIsPreviewing(false);
    }
  }

  return (
    <div className="space-y-6">
      {disabled ? (
        <Alert variant="warning">
          This version is published. Open a new draft to change its fields.
        </Alert>
      ) : null}

      <div className="space-y-4">
        {fields.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No fields yet. Add the first one below.
          </p>
        ) : (
          sorted.map((field, index) => (
              <fieldset key={field.id ?? index} disabled={disabled} className="contents">
                <FieldRow
                  field={field}
                  index={index}
                  total={fields.length}
                  earlier={sorted.slice(0, index)}
                  onChange={(next) => updateAt(index, next)}
                  onRemove={() => removeAt(index)}
                  onMove={(direction) => moveAt(index, direction)}
                />
              </fieldset>
            ))
        )}
        {!disabled ? (
          <Button type="button" variant="outline" onClick={addField}>
            <Plus className="size-4" aria-hidden="true" />
            Add field
          </Button>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Preview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {previewFailure ? <Alert variant="error">{previewFailure}</Alert> : null}
          {previewNotice ? <Alert variant="success">{previewNotice}</Alert> : null}
          {fields.length === 0 ? (
            <p className="text-sm text-ink-muted">
              Add a field to try sample values against it.
            </p>
          ) : (
            <div className="space-y-4">
              <FieldRenderer
                // The preview only needs shape, not the server's id.
                fields={sorted
                  .filter((field) => field.key)
                  .map((field) => ({ ...field, id: field.id ?? field.key }))}
                values={previewValues}
                errors={previewErrors}
                onChange={(key, value) =>
                  setPreviewValues((current) => ({ ...current, [key]: value }))
                }
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => void runPreview()}
                disabled={isPreviewing}
              >
                {isPreviewing ? "Checking…" : "Check values"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
