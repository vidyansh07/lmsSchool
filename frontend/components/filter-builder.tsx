'use client';

/**
 * Ask a list a question of your own.
 *
 * Every list screen here shipped a handful of fixed filters — a status
 * dropdown, a city box, whatever the screen was first built for. That answers
 * the questions somebody thought of in advance, and an operations team spends
 * its day on the ones nobody did: "students from any college whose name
 * contains Arya, registered this month, with no roll number".
 *
 * The fields come from the server, never from a copy kept here. That is the
 * point: the list endpoint enforces an allowlist, and this is built from the
 * same declaration, so the bar cannot offer a field or an operator that would
 * be quietly ignored. A filter feature usually rots the other way round — the
 * server drops a field, the control stays, and the list stops narrowing while
 * still looking like it works.
 *
 * Conditions become ordinary query parameters (`city__icontains=jai`), so a
 * filtered list is a URL somebody can bookmark or send to a colleague, and the
 * existing saved-views feature stores them without knowing anything about this
 * component.
 *
 * One field may be asked one question at a time. Two conditions on the same
 * field would mean `city is Jaipur AND city is Pune`, which is always empty,
 * and the parameter shape cannot carry both anyway. Picking the same field
 * twice replaces the first.
 */
import { Check, Filter, Plus, X } from 'lucide-react';
import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Select } from '@/components/ui/select';
import { cn } from '@/lib/utils';

export interface FilterOperator {
  value: string;
  label: string;
}

export interface FilterChoice {
  value: string;
  label: string;
}

export interface FilterFieldSpec {
  name: string;
  label: string;
  kind: 'text' | 'choice' | 'number' | 'date' | 'boolean' | 'uuid';
  operators: FilterOperator[];
  choices?: FilterChoice[] | null;
}

export interface FilterCondition {
  field: string;
  operator: string;
  value: string;
}

/**
 * The query parameter one condition becomes.
 *
 * `exact` keeps the bare field name, matching the server: every saved link in
 * the product already spells it that way.
 */
export function parameterFor(condition: FilterCondition): string {
  return condition.operator === 'exact'
    ? condition.field
    : `${condition.field}__${condition.operator}`;
}

/** Conditions as a query object, ready for `setQuery`. */
export function toQuery(conditions: FilterCondition[]): Record<string, string> {
  const query: Record<string, string> = {};
  for (const condition of conditions) {
    if (!condition.value) continue;
    query[parameterFor(condition)] = condition.value;
  }
  return query;
}

/**
 * Read conditions back out of a query, so a bookmarked URL arrives with its
 * filter bar already filled in rather than looking unfiltered while the list
 * underneath is narrowed — the discrepancy that makes people distrust a filter.
 */
export function fromQuery(
  query: Record<string, unknown>,
  fields: FilterFieldSpec[],
): FilterCondition[] {
  const byName = new Map(fields.map((field) => [field.name, field]));
  const conditions: FilterCondition[] = [];
  for (const [key, raw] of Object.entries(query)) {
    if (raw === undefined || raw === null || raw === '') continue;
    const value = String(raw);
    const direct = byName.get(key);
    if (direct) {
      conditions.push({ field: key, operator: 'exact', value });
      continue;
    }
    const split = key.lastIndexOf('__');
    if (split <= 0) continue;
    const name = key.slice(0, split);
    const operator = key.slice(split + 2);
    const field = byName.get(name);
    if (field?.operators.some((candidate) => candidate.value === operator)) {
      conditions.push({ field: name, operator, value });
    }
  }
  return conditions;
}

/** A condition's wording, for the chip: "College contains Arya". */
function describe(condition: FilterCondition, fields: FilterFieldSpec[]): string {
  const field = fields.find((candidate) => candidate.name === condition.field);
  if (!field) return condition.field;
  const operator = field.operators.find(
    (candidate) => candidate.value === condition.operator,
  );
  if (condition.operator === 'isnull') {
    return `${field.label} ${condition.value === 'true' ? 'is empty' : 'is filled in'}`;
  }
  const choice = field.choices?.find((candidate) => candidate.value === condition.value);
  return `${field.label} ${operator?.label ?? condition.operator} ${choice?.label ?? condition.value}`;
}

export interface FilterBuilderProps {
  fields: FilterFieldSpec[];
  conditions: FilterCondition[];
  onChange: (conditions: FilterCondition[]) => void;
  className?: string;
}

export function FilterBuilder({
  fields,
  conditions,
  onChange,
  className,
}: FilterBuilderProps) {
  const [open, setOpen] = React.useState(false);

  // A field with nothing to ask about is not offered.
  if (fields.length === 0) return null;

  function apply(next: FilterCondition) {
    // One question per field: picking a field already in play replaces it.
    const rest = conditions.filter((condition) => condition.field !== next.field);
    onChange([...rest, next]);
    setOpen(false);
  }

  function remove(field: string) {
    onChange(conditions.filter((condition) => condition.field !== field));
  }

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      {conditions.map((condition) => (
        <Badge key={condition.field} variant="neutral" className="gap-1 pr-1">
          {describe(condition, fields)}
          <button
            type="button"
            onClick={() => remove(condition.field)}
            aria-label={`Remove the filter ${describe(condition, fields)}`}
            className="rounded-full p-0.5 text-ink-muted transition-colors hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-action"
          >
            <X className="size-3" aria-hidden="true" />
          </button>
        </Badge>
      ))}

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            {conditions.length === 0 ? (
              <Filter className="size-3.5" aria-hidden="true" />
            ) : (
              <Plus className="size-3.5" aria-hidden="true" />
            )}
            {conditions.length === 0 ? 'Filter' : 'Add filter'}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80 p-3">
          <ConditionForm fields={fields} onApply={apply} />
        </PopoverContent>
      </Popover>

      {conditions.length > 0 ? (
        <Button variant="ghost" size="sm" onClick={() => onChange([])}>
          Clear all
        </Button>
      ) : null}
    </div>
  );
}

function ConditionForm({
  fields,
  onApply,
}: {
  fields: FilterFieldSpec[];
  onApply: (condition: FilterCondition) => void;
}) {
  const [fieldName, setFieldName] = React.useState(fields[0]?.name ?? '');
  const field = fields.find((candidate) => candidate.name === fieldName) ?? fields[0];
  const [operator, setOperator] = React.useState(field?.operators[0]?.value ?? 'exact');
  const [value, setValue] = React.useState('');

  function chooseField(name: string) {
    const next = fields.find((candidate) => candidate.name === name);
    setFieldName(name);
    // The operators change with the field, so an operator carried over from
    // the previous one may not exist here.
    setOperator(next?.operators[0]?.value ?? 'exact');
    setValue('');
  }

  if (!field) return null;

  // "is empty" asks about absence, so it takes yes or no rather than a value.
  const isNullQuestion = operator === 'isnull';
  const canApply = isNullQuestion ? value !== '' : value.trim() !== '';

  return (
    <form
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!canApply) return;
        onApply({ field: fieldName, operator, value: value.trim() });
      }}
    >
      <label className="block text-2xs font-semibold uppercase tracking-[0.12em] text-ink-faint">
        Field
        <Select
          value={fieldName}
          onChange={(event) => chooseField(event.target.value)}
          className="mt-1 w-full font-normal normal-case tracking-normal"
        >
          {fields.map((candidate) => (
            <option key={candidate.name} value={candidate.name}>
              {candidate.label}
            </option>
          ))}
        </Select>
      </label>

      <label className="block text-2xs font-semibold uppercase tracking-[0.12em] text-ink-faint">
        Condition
        <Select
          value={operator}
          onChange={(event) => {
            setOperator(event.target.value);
            setValue('');
          }}
          className="mt-1 w-full font-normal normal-case tracking-normal"
        >
          {field.operators.map((candidate) => (
            <option key={candidate.value} value={candidate.value}>
              {candidate.label}
            </option>
          ))}
        </Select>
      </label>

      <label className="block text-2xs font-semibold uppercase tracking-[0.12em] text-ink-faint">
        Value
        {isNullQuestion ? (
          <Select
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className="mt-1 w-full font-normal normal-case tracking-normal"
          >
            <option value="">Choose…</option>
            <option value="true">Yes — it is empty</option>
            <option value="false">No — it is filled in</option>
          </Select>
        ) : field.choices && field.choices.length > 0 ? (
          <Select
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className="mt-1 w-full font-normal normal-case tracking-normal"
          >
            <option value="">Choose…</option>
            {field.choices.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </Select>
        ) : (
          <Input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            type={field.kind === 'date' ? 'date' : field.kind === 'number' ? 'number' : 'text'}
            placeholder={field.kind === 'date' ? '' : `${field.label}…`}
            className="mt-1 w-full font-normal normal-case tracking-normal"
          />
        )}
      </label>

      <Button type="submit" size="sm" disabled={!canApply} className="w-full gap-1.5">
        <Check className="size-3.5" aria-hidden="true" />
        Apply
      </Button>
    </form>
  );
}
