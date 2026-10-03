"use client";

/**
 * Renders the right input for each form-field type, including the
 * Meritto-style ones: time, star rating, consent tick box, hidden value,
 * heading, and a dropdown whose choices depend on another field's answer.
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

import { useState } from "react";
import { Download, Star } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { errorMessage } from "@/lib/api";
import { formUploadUrl, uploadFormFile } from "@/lib/forms";
import { cn } from "@/lib/utils";
import type {
  FormField,
  FormFieldDependentOptions,
  FormFieldOption,
  FormFieldOptions,
  FormFieldShowIf,
} from "@/types/api";

/** The value shape carried for each field, keyed by `FormField.key`. */
export type FormValues = Record<string, unknown>;

function optionList(field: Pick<FormField, "options">): FormFieldOption[] {
  return Array.isArray(field.options) ? field.options : [];
}

function isDependentOptions(
  options: FormFieldOptions,
): options is FormFieldDependentOptions {
  return (
    !!options &&
    !Array.isArray(options) &&
    typeof (options as FormFieldDependentOptions).parent === "string"
  );
}

/** The related model of a `relation` field, or null for any other shape. */
export function relationModel(options: FormFieldOptions): string | null {
  if (!options || Array.isArray(options)) return null;
  return "model" in options ? options.model : null;
}

/** The choices a `dependent_select` offers for the current answer of the
 *  field it depends on — empty until that field is answered. */
export function dependentChoices(
  field: Pick<FormField, "options">,
  values: FormValues,
): FormFieldOption[] {
  if (!isDependentOptions(field.options)) return [];
  const parentValue = values[field.options.parent];
  if (parentValue === undefined || parentValue === null || parentValue === "") return [];
  return field.options.choices[String(parentValue)] ?? [];
}

/** Every choice a field could ever take — a dependent select's choices for
 *  every parent answer, flattened. Used where no parent answer is known. */
export function allChoices(field: Pick<FormField, "options">): FormFieldOption[] {
  if (Array.isArray(field.options)) return field.options;
  if (isDependentOptions(field.options)) {
    const seen = new Map<string, FormFieldOption>();
    for (const list of Object.values(field.options.choices)) {
      for (const option of list) if (!seen.has(option.value)) seen.set(option.value, option);
    }
    return Array.from(seen.values());
  }
  return [];
}

function isBlank(value: unknown): boolean {
  return (
    value === undefined ||
    value === null ||
    value === "" ||
    value === false ||
    (Array.isArray(value) && value.length === 0)
  );
}

function showIfMatches(rule: FormFieldShowIf, parentValue: unknown): boolean {
  const op = rule.op ?? "eq";
  const target = rule.value;
  if (op === "filled") return !isBlank(parentValue);
  if (op === "empty") return isBlank(parentValue);
  const targets = Array.isArray(target) ? target.map(String) : [];
  if (Array.isArray(parentValue)) {
    const picks = parentValue.map(String);
    if (op === "eq") return picks.includes(String(target));
    if (op === "ne") return !picks.includes(String(target));
    if (op === "in") return picks.some((pick) => targets.includes(pick));
    if (op === "not_in") return !picks.some((pick) => targets.includes(pick));
    return false;
  }
  const missing = parentValue === undefined;
  // Compare as the server does: a boolean against a boolean, anything else
  // as text (select answers are always strings).
  if (op === "eq") {
    if (typeof target === "boolean") return parentValue === target;
    return !missing && parentValue !== null && String(parentValue) === String(target);
  }
  if (op === "ne") {
    if (typeof target === "boolean") return parentValue !== target;
    return missing || parentValue === null || String(parentValue) !== String(target);
  }
  if (op === "in") return !missing && parentValue !== null && targets.includes(String(parentValue));
  if (op === "not_in") return missing || parentValue === null || !targets.includes(String(parentValue));
  return false;
}

/**
 * The keys of every field shown for these answers — the same rule the
 * server applies (`apps/forms/validation.py::visible_field_keys`): a field is
 * shown when it has no `show_if`, or when the field it names is itself shown
 * and that field's answer matches. A hidden field is never required and its
 * value is not sent.
 */
export function visibleFieldKeys(
  fields: Pick<FormField, "key" | "show_if">[],
  values: FormValues,
): Set<string> {
  const byKey = new Map(fields.map((field) => [field.key, field]));
  const memo = new Map<string, boolean>();
  function visible(key: string, trail: Set<string>): boolean {
    const known = memo.get(key);
    if (known !== undefined) return known;
    const field = byKey.get(key);
    if (!field || trail.has(key)) return false;
    const rule = field.show_if ?? {};
    let result = true;
    if (rule.field) {
      const nextTrail = new Set(trail).add(key);
      result = visible(rule.field, nextTrail) && showIfMatches(rule, values[rule.field]);
    }
    memo.set(key, result);
    return result;
  }
  return new Set(fields.filter((field) => visible(field.key, new Set())).map((field) => field.key));
}

/**
 * The answers to send: only fields that are shown and answered, with
 * numbers as numbers and a local date-time as an ISO instant. Inputs keep
 * typed text in state; this is the one place it is turned into what the
 * server validates.
 */
export function valuesForSubmit(fields: FormField[], values: FormValues): FormValues {
  const shown = visibleFieldKeys(fields, values);
  const out: FormValues = {};
  for (const field of fields) {
    if (!shown.has(field.key) || field.type === "heading") continue;
    const value = values[field.key];
    if (value === undefined || value === null || value === "") continue;
    if (field.type === "number" && typeof value === "string") {
      const parsed = Number(value);
      out[field.key] = Number.isNaN(parsed) ? value : parsed;
    } else if (field.type === "datetime" && typeof value === "string" && !/[zZ]|[+-]\d\d:\d\d$/.test(value)) {
      const parsed = new Date(value);
      out[field.key] = Number.isNaN(parsed.getTime()) ? value : parsed.toISOString();
    } else {
      out[field.key] = value;
    }
  }
  return out;
}

function RatingControl({
  id,
  label,
  value,
  max,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  value: unknown;
  max: number;
  disabled: boolean;
  onChange?: (value: unknown) => void;
}) {
  const current = typeof value === "number" ? value : Number(value) || 0;
  return (
    <div id={id} role="group" aria-label={label} className="flex items-center gap-1">
      {Array.from({ length: max }, (_, index) => index + 1).map((score) => (
        <button
          key={score}
          type="button"
          disabled={disabled}
          aria-pressed={current === score}
          aria-label={`${score} of ${max}`}
          onClick={() => onChange?.(current === score ? null : score)}
          className={cn(
            "rounded-control p-1 text-ink-faint transition-colors hover:text-action",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
            score <= current && "text-action",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          <Star
            className="size-5"
            aria-hidden="true"
            fill={score <= current ? "currentColor" : "none"}
          />
        </button>
      ))}
      {current ? (
        <span className="ml-1 text-xs tabular-nums text-ink-muted">
          {current}/{max}
        </span>
      ) : null}
    </div>
  );
}

function UploadControl({
  id,
  value,
  accept,
  disabled,
  readOnly,
  onChange,
}: {
  id: string;
  value: unknown;
  accept?: string[];
  disabled: boolean;
  /** A submitted answer: a download link instead of a file picker. */
  readOnly: boolean;
  onChange?: (value: unknown) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const uploadId = typeof value === "string" && value ? value : null;

  if (readOnly) {
    return uploadId ? (
      <a
        href={formUploadUrl(uploadId)}
        className="inline-flex items-center gap-1.5 text-sm text-action hover:underline"
      >
        <Download className="size-4" aria-hidden="true" />
        Download file
      </a>
    ) : (
      <p className="text-sm text-ink-muted">No file.</p>
    );
  }

  return (
    <div className="space-y-1.5">
      <Input
        id={id}
        type="file"
        accept={accept?.join(",")}
        disabled={disabled || busy}
        onChange={async (event) => {
          const file = event.target.files?.[0];
          if (!file) {
            onChange?.(null);
            return;
          }
          setBusy(true);
          setError(null);
          try {
            const upload = await uploadFormFile(file);
            setFilename(upload.filename);
            onChange?.(upload.id);
          } catch (cause) {
            setError(errorMessage(cause));
            onChange?.(null);
          } finally {
            setBusy(false);
          }
        }}
      />
      {busy ? <p className="text-2xs text-ink-faint">Uploading…</p> : null}
      {!busy && uploadId ? (
        <p className="text-2xs text-ink-faint">
          Uploaded{filename ? `: ${filename}` : ""}.
        </p>
      ) : null}
      {error ? <p className="text-2xs font-medium text-danger">{error}</p> : null}
    </div>
  );
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
  values = {},
}: {
  field: FormField;
  value: unknown;
  onChange?: (value: unknown) => void;
  readOnly?: boolean;
  /** Every current answer — a `dependent_select` reads its parent's here. */
  values?: FormValues;
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
        <UploadControl
          id={id}
          value={value}
          accept={field.validation.accept}
          disabled={disabled}
          readOnly={readOnly}
          onChange={onChange}
        />
      );
    case "relation": {
      const model = relationModel(field.options);
      return (
        <Input
          id={id}
          type="text"
          value={toStringValue(value)}
          disabled={disabled}
          placeholder={model ? `${model} id` : "Related record id"}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    }
    case "time":
      return (
        <Input
          id={id}
          type="time"
          value={toStringValue(value)}
          disabled={disabled}
          min={typeof field.validation.min === "string" ? field.validation.min : undefined}
          max={typeof field.validation.max === "string" ? field.validation.max : undefined}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    case "rating":
      return (
        <RatingControl
          id={id}
          label={field.label}
          value={value}
          max={typeof field.validation.max === "number" ? field.validation.max : 5}
          disabled={disabled}
          onChange={onChange}
        />
      );
    case "consent":
      return (
        <Checkbox
          id={id}
          checked={value === true}
          disabled={disabled}
          onCheckedChange={(checked) => onChange?.(checked)}
        />
      );
    case "hidden":
      return readOnly ? (
        <p id={id} className="text-sm text-ink">
          {toStringValue(value) || "—"}
        </p>
      ) : (
        <input id={id} type="hidden" value={toStringValue(value)} readOnly />
      );
    case "heading":
      return null;
    case "dependent_select": {
      const choices = dependentChoices(field, values);
      const waiting = choices.length === 0;
      return (
        <Select
          id={id}
          value={toStringValue(value)}
          disabled={disabled || waiting}
          onChange={(event) => onChange?.(event.target.value)}
        >
          <option value="">{waiting ? "Answer the question above first" : "Choose…"}</option>
          {choices.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      );
    }
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
  const shown = visibleFieldKeys(fields, values);
  const visible = (
    studentOnly ? fields.filter((field) => field.visible_to_student) : fields
  )
    .filter((field) => shown.has(field.key))
    // A hidden value is carried along, never asked for; in a read-only
    // summary it is shown only when it holds something.
    .filter((field) => field.type !== "hidden" || (readOnly && !isBlank(values[field.key])))
    .slice()
    .sort((a, b) => a.order - b.order);

  if (visible.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        This form has no fields to show.
      </p>
    );
  }

  /** A change to a field clears any dependent dropdown whose answer is no
   *  longer one of the choices the new answer offers. */
  function handleChange(key: string, value: unknown) {
    if (!onChange) return;
    onChange(key, value);
    const next = { ...values, [key]: value };
    for (const field of fields) {
      if (
        field.type === "dependent_select" &&
        isDependentOptions(field.options) &&
        field.options.parent === key &&
        !isBlank(values[field.key]) &&
        !dependentChoices(field, next).some((option) => option.value === values[field.key])
      ) {
        onChange(field.key, "");
      }
    }
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
          {/* A group that opens with its own heading field needs no second title. */}
          {group && groupFields[0]?.type !== "heading" ? (
            <h3 className="text-sm font-semibold text-ink-muted">
              {group}
            </h3>
          ) : null}
          {groupFields.map((field) => {
            const id = `form-field-${field.key}`;
            const change = onChange ? (value: unknown) => handleChange(field.key, value) : undefined;
            if (field.type === "heading") {
              return (
                <div key={field.id} className="space-y-1 border-b border-line pb-2">
                  <h3 className="text-sm font-semibold text-ink">{field.label}</h3>
                  {field.help ? <p className="text-xs text-ink-muted">{field.help}</p> : null}
                </div>
              );
            }
            if (field.type === "consent") {
              const error = errors?.[field.key];
              return (
                <div key={field.id} className="space-y-1.5">
                  <div className="flex items-start gap-3">
                    <FieldControl
                      field={field}
                      value={values[field.key]}
                      values={values}
                      readOnly={readOnly}
                      onChange={change}
                    />
                    <label htmlFor={id} className="text-sm text-ink">
                      {field.label}
                      {field.required ? (
                        <span className="ml-1 text-danger" aria-hidden="true">
                          *
                        </span>
                      ) : null}
                    </label>
                  </div>
                  {error ? (
                    <p id={`${id}-error`} className="text-2xs font-medium text-danger">
                      {error}
                    </p>
                  ) : null}
                </div>
              );
            }
            return (
              <Field
                key={field.id}
                label={field.label}
                htmlFor={id}
                hint={field.help || undefined}
                required={field.required}
                error={errors?.[field.key]}
              >
                <FieldControl
                  field={field}
                  value={values[field.key]}
                  values={values}
                  readOnly={readOnly}
                  onChange={change}
                />
              </Field>
            );
          })}
        </div>
      ))}
    </div>
  );
}
