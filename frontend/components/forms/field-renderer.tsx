"use client";

/**
 * Renders the right input for one of the 17 form-field types.
 *
 * Presentational only — no fetching, no forms-admin state. This is the piece
 * later phases (student-custom fields on the registration wizard, the
 * Student 360 activity form) reuse as-is: give it a published version's
 * `fields`, the current `values`, and a change handler, and it renders a
 * form; give it `readOnly` and it renders a summary view of an already-
 * submitted response.
 *
 * `relation` fields render as a plain text input carrying the related
 * record's id. The 17-type contract (`DATA_MODEL.md` §4, `FORM_CATALOG.md`)
 * pins `options: {model: "student"|"trainer"|"batch"}` for a relation field
 * but does not pin a lookup/search endpoint — a typeahead picker is a
 * reasonable follow-up once that endpoint exists, not something to invent
 * here.
 */

import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { FormField, FormFieldOption } from "@/types/api";

/** The value shape carried for each field, keyed by `FormField.key`. */
export type FormValues = Record<string, unknown>;

function optionList(field: FormField): FormFieldOption[] {
  return Array.isArray(field.options) ? field.options : [];
}

function toStringValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((entry) => String(entry)) : [];
}

/** One field's own control, with no label/error wrapper — used both by
 *  {@link FieldRenderer} (which adds the `Field` wrapper) and by anything
 *  that wants to lay controls out itself. */
export function FieldControl({
  field,
  value,
  onChange,
  readOnly = false,
}: {
  field: FormField;
  value: unknown;
  onChange?: (value: unknown) => void;
  readOnly?: boolean;
}) {
  const id = `form-field-${field.key}`;
  const disabled = readOnly || !onChange;

  switch (field.type) {
    case "textarea":
    case "richtext":
      return (
        <Textarea
          id={id}
          value={toStringValue(value)}
          disabled={disabled}
          maxLength={field.validation.max_length}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "number":
      return (
        <Input
          id={id}
          type="number"
          step="1"
          value={toStringValue(value)}
          disabled={disabled}
          min={field.validation.min}
          max={field.validation.max}
          // Kept as the raw string, never `valueAsNumber`: an emptied input
          // reports `NaN`, which nothing in this app puts in state — the
          // server coerces on submit, same as `decimal` below.
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "decimal":
      return (
        <Input
          id={id}
          type="number"
          step="0.01"
          value={toStringValue(value)}
          disabled={disabled}
          min={field.validation.min}
          max={field.validation.max}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "date":
      return (
        <Input
          id={id}
          type="date"
          value={toStringValue(value)}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "datetime":
      return (
        <Input
          id={id}
          type="datetime-local"
          value={toStringValue(value)}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "boolean":
      return (
        <Checkbox
          id={id}
          checked={Boolean(value)}
          disabled={disabled}
          onCheckedChange={(checked) => onChange?.(checked)}
        />
      );
    case "select":
      return (
        <Select
          id={id}
          value={toStringValue(value)}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.value)}
        >
          <option value="">Choose…</option>
          {optionList(field).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      );
    case "radio":
      return (
        <RadioGroup
          value={toStringValue(value)}
          onValueChange={(next) => onChange?.(next)}
          disabled={disabled}
          aria-label={field.label}
        >
          {optionList(field).map((option) => (
            <label
              key={option.value}
              className="flex items-center gap-2 text-sm"
            >
              <RadioGroupItem value={option.value} />
              {option.label}
            </label>
          ))}
        </RadioGroup>
      );
    case "multiselect":
    case "checkbox": {
      const selected = new Set(toStringArray(value));
      return (
        <div className="space-y-1.5" role="group" aria-label={field.label}>
          {optionList(field).map((option) => (
            <label
              key={option.value}
              className="flex items-center gap-2 text-sm"
            >
              <Checkbox
                checked={selected.has(option.value)}
                disabled={disabled}
                onCheckedChange={(checked) => {
                  const next = new Set(selected);
                  if (checked) next.add(option.value);
                  else next.delete(option.value);
                  onChange?.(Array.from(next));
                }}
              />
              {option.label}
            </label>
          ))}
        </div>
      );
    }
    case "email":
      return (
        <Input
          id={id}
          type="email"
          value={toStringValue(value)}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "phone":
      return (
        <Input
          id={id}
          type="tel"
          value={toStringValue(value)}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "url":
      return (
        <Input
          id={id}
          type="url"
          value={toStringValue(value)}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "file":
    case "image":
      return (
        <Input
          id={id}
          type="file"
          disabled={disabled}
          accept={field.validation.accept?.join(",")}
          onChange={(event) => onChange?.(event.target.files?.[0] ?? null)}
        />
      );
    case "relation":
      return (
        <Input
          id={id}
          type="text"
          value={toStringValue(value)}
          disabled={disabled}
          placeholder={
            field.options && !Array.isArray(field.options)
              ? `${field.options.model} id`
              : "Related record id"
          }
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "text":
    default:
      return (
        <Input
          id={id}
          type="text"
          value={toStringValue(value)}
          disabled={disabled}
          maxLength={field.validation.max_length}
          pattern={field.validation.pattern}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
  }
}

/**
 * A whole form's worth of fields, laid out one per row, grouped by
 * `FormField.group` and ordered by `FormField.order`.
 *
 * `errors` keys by field `key`, matching what `fieldErrors()` (`lib/api.ts`)
 * produces from a `400` preview/submit response.
 */
export function FieldRenderer({
  fields,
  values,
  onChange,
  errors,
  readOnly = false,
  studentOnly = false,
}: {
  fields: FormField[];
  values: FormValues;
  onChange?: (key: string, value: unknown) => void;
  errors?: Record<string, string>;
  readOnly?: boolean;
  /** Only render fields the student may see — for a student-facing screen
   *  rendering a staff-authored form. */
  studentOnly?: boolean;
}) {
  const visible = (
    studentOnly ? fields.filter((field) => field.visible_to_student) : fields
  )
    .slice()
    .sort((a, b) => a.order - b.order);

  if (visible.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        This form has no fields to show.
      </p>
    );
  }

  const groups = new Map<string, FormField[]>();
  for (const field of visible) {
    const key = field.group || "";
    const bucket = groups.get(key) ?? [];
    bucket.push(field);
    groups.set(key, bucket);
  }

  return (
    <div className="space-y-6">
      {Array.from(groups.entries()).map(([group, groupFields]) => (
        <div key={group || "__default"} className="space-y-4">
          {group ? (
            <h3 className="text-sm font-semibold text-muted-foreground">
              {group}
            </h3>
          ) : null}
          {groupFields.map((field) => (
            <Field
              key={field.id}
              label={field.label}
              htmlFor={`form-field-${field.key}`}
              hint={field.help || undefined}
              required={field.required}
              error={errors?.[field.key]}
            >
              <FieldControl
                field={field}
                value={values[field.key]}
                readOnly={readOnly}
                onChange={
                  onChange ? (value) => onChange(field.key, value) : undefined
                }
              />
            </Field>
          ))}
        </div>
      ))}
    </div>
  );
}
