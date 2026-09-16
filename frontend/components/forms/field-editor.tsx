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
import { FieldControl, type FormValues } from "@/components/forms/field-renderer";
import { fieldErrors } from "@/lib/api";
import { FORM_FIELD_CHOICE_TYPES, FORM_FIELD_TYPE_OPTIONS } from "@/lib/labels";
import { previewForm } from "@/lib/forms";
import type {
  FormFieldInput,
  FormFieldOption,
  FormFieldRelationModel,
  FormFieldType,
} from "@/types/api";

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
    default:
      return [];
  }
}

function FieldRow({
  field,
  index,
  total,
  onChange,
  onRemove,
  onMove,
}: {
  field: FormFieldInput;
  index: number;
  total: number;
  onChange: (next: FormFieldInput) => void;
  onRemove: () => void;
  onMove: (direction: -1 | 1) => void;
}) {
  const uid = useId();
  const validationKeys = validationKeysFor(field.type);
  const isChoiceType = FORM_FIELD_CHOICE_TYPES.includes(field.type);

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
                      : null,
                  validation: {},
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
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={field.required}
              onCheckedChange={(checked) => onChange({ ...field, required: checked })}
            />
            Required
          </label>
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

        {field.type === "relation" ? (
          <Field label="Related model" htmlFor={`${uid}-relation-model`}>
            <Select
              id={`${uid}-relation-model`}
              value={
                field.options && !Array.isArray(field.options)
                  ? field.options.model
                  : "student"
              }
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
              <Field label="Max" htmlFor={`${uid}-max`}>
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
      const result = await previewForm(slug, previewValues);
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
          <p className="text-sm text-muted-foreground">
            No fields yet. Add the first one below.
          </p>
        ) : (
          fields
            .slice()
            .sort((a, b) => a.order - b.order)
            .map((field, index) => (
              <fieldset key={field.id ?? index} disabled={disabled} className="contents">
                <FieldRow
                  field={field}
                  index={index}
                  total={fields.length}
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
            <p className="text-sm text-muted-foreground">
              Add a field to try sample values against it.
            </p>
          ) : (
            <div className="space-y-4">
              {fields
                .slice()
                .sort((a, b) => a.order - b.order)
                .filter((field) => field.key)
                .map((field) => (
                  <Field
                    key={field.key}
                    label={field.label || field.key}
                    htmlFor={`preview-${field.key}`}
                    error={previewErrors[field.key]}
                  >
                    <FieldControl
                      // The preview only needs shape, not the server's id.
                      field={{ ...field, id: field.id ?? field.key }}
                      value={previewValues[field.key]}
                      onChange={(value) =>
                        setPreviewValues((current) => ({
                          ...current,
                          [field.key]: value,
                        }))
                      }
                    />
                  </Field>
                ))}
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
