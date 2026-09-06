'use client';

/**
 * The register, marked without a mouse.
 *
 * A trainer taking a register in front of a room does not tab through cells —
 * they run a finger down a class list and call out a mark per name. `P` / `A`
 * / `L` / `E` on the focused row is that same motion: no click, no menu, just
 * the one row and the one key. Arrow keys move down the list the same way.
 * "Mark all present" exists because that is how a register is actually taken
 * — everyone is here until proven otherwise — so it front-loads the common
 * case and leaves only the exceptions to correct.
 *
 * The roving tabindex here (one row is `tabIndex=0`, the rest `-1`) matches
 * `data-table.tsx`'s pattern for the same reason: Tab should move past the
 * whole register in one step, not through every row. The four per-row status
 * buttons are deliberately `tabIndex=-1` — reachable by click, not by Tab —
 * because this table has exactly one keyboard entry point (the row) and
 * letting Tab wander into four buttons per row would turn a twenty-row class
 * into an eighty-stop tab sequence. The focus ring on the active row is
 * heavier than `data-table.tsx`'s own (`ring-2` instead of `ring-1`, plus a
 * tint) on purpose: every other table in this app is click-first with
 * keyboard as an alternative, but here the blind keypress *is* the primary
 * interaction, so which row it will land on has to be unmistakable.
 *
 * Per-student notes are deliberately absent. `/teaching/sessions/[id]`
 * already owns detailed register editing, notes included; duplicating that
 * here would also mean a fifth tab stop per row, which is the one thing this
 * screen exists to avoid.
 *
 * Online/offline counts are not shown here despite belonging next to the
 * P/A/L/E tally in spirit: no endpoint this screen can reach reports how a
 * student joined (see `lib/dsr.ts` and the DSR panel for where that number is
 * actually confirmed). Rendering a guess would violate the one rule that
 * matters more than density — never show a number that was not really
 * computed — so the slot renders the app's standard "not available" fallback
 * instead of inventing one.
 */
import {
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';

import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { ATTENDANCE_OPTIONS, ATTENDANCE_STATUS_LABEL } from '@/lib/academic-labels';
import { fallback, formatNumber, UNKNOWN } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { AttendanceStatus, RegisterEntry } from '@/types/api';

/** First-letter chord per status — the whole point of this screen. */
const KEY_TO_STATUS: Record<string, AttendanceStatus> = {
  p: 'present',
  a: 'absent',
  l: 'late',
  e: 'excused',
};

export interface RegisterEditorProps {
  entries: RegisterEntry[];
  marks: Record<string, AttendanceStatus>;
  onMark: (enrollmentId: string, status: AttendanceStatus) => void;
  onMarkAllPresent: () => void;
  canMark: boolean;
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}

function studentLabel(entry: RegisterEntry): string {
  return fallback(entry.full_name, UNKNOWN);
}

export function RegisterEditor({
  entries,
  marks,
  onMark,
  onMarkAllPresent,
  canMark,
  isLoading = false,
  error = null,
  onRetry,
}: RegisterEditorProps) {
  const [rawFocusedIndex, setFocusedIndex] = useState(0);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  // Clamped during render, not an effect — the same "adjust state while
  // rendering" pattern `data-table.tsx` uses when its row count shrinks.
  const focusedIndex = entries.length === 0 ? 0 : Math.min(rawFocusedIndex, entries.length - 1);
  if (focusedIndex !== rawFocusedIndex) setFocusedIndex(focusedIndex);

  const counts = useMemo(() => {
    const tally = { present: 0, absent: 0, late: 0, excused: 0, unmarked: 0 };
    for (const entry of entries) {
      const status = marks[entry.enrollment_id];
      if (status) tally[status] += 1;
      else tally.unmarked += 1;
    }
    return tally;
  }, [entries, marks]);

  function focusRow(index: number) {
    setFocusedIndex(index);
    rowRefs.current[index]?.focus();
  }

  function handleRowKeyDown(
    event: ReactKeyboardEvent<HTMLTableRowElement>,
    index: number,
    enrollmentId: string,
  ) {
    // A held modifier means the browser or OS owns this keystroke (Cmd+P is
    // "print", not "mark present").
    if (event.ctrlKey || event.metaKey || event.altKey) return;

    const status = KEY_TO_STATUS[event.key.toLowerCase()];
    if (status) {
      if (!canMark) return;
      event.preventDefault();
      onMark(enrollmentId, status);
      return;
    }

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        focusRow(Math.min(index + 1, entries.length - 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        focusRow(Math.max(index - 1, 0));
        break;
      case 'Home':
        event.preventDefault();
        focusRow(0);
        break;
      case 'End':
        event.preventDefault();
        focusRow(entries.length - 1);
        break;
      default:
        break;
    }
  }

  if (isLoading) return <LoadingState label="Loading the register…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load the register"
        message={error.message}
        requestId={error.requestId}
        onRetry={onRetry}
      />
    );
  }
  if (entries.length === 0) {
    return (
      <EmptyState
        title="No students on this register"
        description="Nobody is enrolled on this batch yet, so there is nothing to mark."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button type="button" variant="outline" size="sm" onClick={onMarkAllPresent} disabled={!canMark}>
          Mark all present
        </Button>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span>Focused row:</span>
          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.65rem]">P</kbd>
          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.65rem]">A</kbd>
          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.65rem]">L</kbd>
          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.65rem]">E</kbd>
        </div>
      </div>

      <div
        aria-live="polite"
        aria-atomic="true"
        className="flex flex-wrap gap-x-4 gap-y-1 rounded-[var(--radius-card)] border border-border bg-muted/50 px-4 py-2.5 text-sm"
      >
        <span>
          <strong className="tabular-nums">{formatNumber(counts.present)}</strong> present
        </span>
        <span>
          <strong className="tabular-nums">{formatNumber(counts.absent)}</strong> absent
        </span>
        <span>
          <strong className="tabular-nums">{formatNumber(counts.late)}</strong> late
        </span>
        <span>
          <strong className="tabular-nums">{formatNumber(counts.excused)}</strong> excused
        </span>
        {counts.unmarked > 0 ? (
          <span className="text-warning">
            <strong className="tabular-nums">{formatNumber(counts.unmarked)}</strong> unmarked
          </span>
        ) : null}
        <span className="text-muted-foreground" title="Not reported by the API this screen can reach — see the DSR section below.">
          Online: {fallback(undefined)} · Offline: {fallback(undefined)}
        </span>
      </div>

      {!canMark ? (
        <p className="text-sm text-muted-foreground">
          This class cannot be marked right now — it may be cancelled, or it may not have started.
        </p>
      ) : null}

      <TableWrapper>
        <Table>
          <caption className="sr-only">Class register, one row per student</caption>
          <thead>
            <tr>
              <Th>Student</Th>
              <Th>Attendance</Th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => {
              const status = marks[entry.enrollment_id] ?? null;
              const isFocused = focusedIndex === index;
              return (
                <tr
                  key={entry.enrollment_id}
                  ref={(node) => {
                    rowRefs.current[index] = node;
                  }}
                  tabIndex={isFocused ? 0 : -1}
                  aria-label={`${studentLabel(entry)}, ${
                    status ? ATTENDANCE_STATUS_LABEL[status] : 'unmarked'
                  }. Press P for present, A for absent, L for late, E for excused.`}
                  onFocus={() => setFocusedIndex(index)}
                  onKeyDown={(event) => handleRowKeyDown(event, index, entry.enrollment_id)}
                  className={cn(
                    'cursor-default outline-none',
                    isFocused && 'bg-accent/40 ring-2 ring-inset ring-primary',
                  )}
                >
                  <Td>
                    <div className="font-medium">{studentLabel(entry)}</div>
                    <div className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
                      {fallback(entry.student_code)}
                      {entry.was_corrected ? <Badge variant="warning">Corrected</Badge> : null}
                      {entry.enrollment_status && entry.enrollment_status !== 'active' ? (
                        <Badge variant="neutral">{entry.enrollment_status}</Badge>
                      ) : null}
                    </div>
                  </Td>
                  <Td>
                    <div
                      role="radiogroup"
                      aria-label={`Attendance for ${studentLabel(entry)}`}
                      className="flex flex-wrap gap-1"
                    >
                      {ATTENDANCE_OPTIONS.map((option) => {
                        const active = status === option.value;
                        return (
                          <Button
                            key={option.value}
                            type="button"
                            role="radio"
                            aria-checked={active}
                            tabIndex={-1}
                            size="sm"
                            variant={active ? 'primary' : 'outline'}
                            disabled={!canMark}
                            onClick={() => onMark(entry.enrollment_id, option.value)}
                          >
                            {option.label}
                          </Button>
                        );
                      })}
                    </div>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </TableWrapper>
    </div>
  );
}
