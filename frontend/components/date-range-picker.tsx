'use client';

/**
 * A date range for a report or a filtered list — presets first, custom range
 * as the escape hatch.
 *
 * "Presets are what people actually click" is the brief, so the two native
 * date inputs are a secondary row rather than the default view: opening this
 * control to a pair of empty date fields makes every use start with two
 * decisions ("what is my start date, what is my end date") when the honest
 * answer nine times out of ten is "this week" or "last 30 days".
 *
 * Emits plain ISO day strings (`YYYY-MM-DD`), matching what `lib/api.ts`'s
 * query-string helper and the backend's date filters already expect —
 * nothing here introduces a second date representation.
 */
import { useId, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export interface DateRange {
  start: string;
  end: string;
}

export type DateRangePresetId =
  | 'today'
  | 'this-week'
  | 'last-7-days'
  | 'last-30-days'
  | 'this-month'
  | 'this-term'
  | 'custom';

function toIsoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function startOfWeek(date: Date): Date {
  // Monday-first, matching `WEEKDAY_LABEL` in `lib/batch-labels.ts`.
  const day = date.getDay();
  const diff = (day + 6) % 7;
  const result = new Date(date);
  result.setDate(result.getDate() - diff);
  return result;
}

/**
 * The available presets. `this-term` needs the institution's own term
 * boundaries, which this component does not know — the caller supplies them
 * via `termRange`, and the preset is omitted if none is given rather than
 * guessing at an academic calendar.
 */
function buildPresets(termRange?: DateRange): { id: DateRangePresetId; label: string; range: DateRange }[] {
  const now = new Date();
  const today = toIsoDay(now);

  const presets: { id: DateRangePresetId; label: string; range: DateRange }[] = [
    { id: 'today', label: 'Today', range: { start: today, end: today } },
    {
      id: 'this-week',
      label: 'This week',
      range: { start: toIsoDay(startOfWeek(now)), end: today },
    },
    {
      id: 'last-7-days',
      label: 'Last 7 days',
      range: { start: toIsoDay(new Date(now.getTime() - 6 * 86_400_000)), end: today },
    },
    {
      id: 'last-30-days',
      label: 'Last 30 days',
      range: { start: toIsoDay(new Date(now.getTime() - 29 * 86_400_000)), end: today },
    },
    {
      id: 'this-month',
      label: 'This month',
      range: { start: toIsoDay(new Date(now.getFullYear(), now.getMonth(), 1)), end: today },
    },
  ];

  if (termRange) presets.push({ id: 'this-term', label: 'This term', range: termRange });
  return presets;
}

export function DateRangePicker({
  value,
  onChange,
  termRange,
  className,
}: {
  value: DateRange;
  onChange: (range: DateRange) => void;
  /** The institution's current term boundaries, if known — enables the "This term" preset. */
  termRange?: DateRange;
  className?: string;
}) {
  const presets = buildPresets(termRange);
  const activePreset = presets.find((preset) => preset.range.start === value.start && preset.range.end === value.end);
  const [showCustom, setShowCustom] = useState(!activePreset);
  const startId = useId();
  const endId = useId();

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div role="group" aria-label="Date range presets" className="flex flex-wrap gap-1.5">
        {presets.map((preset) => (
          <Button
            key={preset.id}
            type="button"
            size="sm"
            variant={activePreset?.id === preset.id && !showCustom ? 'primary' : 'outline'}
            onClick={() => {
              setShowCustom(false);
              onChange(preset.range);
            }}
          >
            {preset.label}
          </Button>
        ))}
        <Button
          type="button"
          size="sm"
          variant={showCustom ? 'primary' : 'outline'}
          aria-expanded={showCustom}
          onClick={() => setShowCustom((current) => !current)}
        >
          Custom range
        </Button>
      </div>

      {showCustom ? (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor={startId} className="mb-1 block text-xs font-medium text-muted-foreground">
              From
            </label>
            <Input
              id={startId}
              type="date"
              value={value.start}
              max={value.end || undefined}
              onChange={(event) => onChange({ ...value, start: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor={endId} className="mb-1 block text-xs font-medium text-muted-foreground">
              To
            </label>
            <Input
              id={endId}
              type="date"
              value={value.end}
              min={value.start || undefined}
              onChange={(event) => onChange({ ...value, end: event.target.value })}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
