'use client';

/**
 * The two-column subject picker from the reference product's New Course
 * screen: a pool on the left, the course's own subjects on the right, and
 * buttons between them.
 *
 * The pool is not a catalogue of subjects, because there is no such table and
 * inventing one would duplicate `Module` — a subject *is* a module of a
 * course here, which is why picking them creates modules in the order shown.
 * The pool is instead the subjects other courses under the same standard
 * already use, which is what makes the two-column shape earn its keep:
 * "Linux Administration" is taught under four courses and should be spelled
 * the same way in all four.
 *
 * Anything not in the pool is typed in, so a new subject is never blocked by
 * the absence of a library entry.
 *
 * Order matters and is the order on the right, moved with Up and Down: a
 * course's modules are positioned, and the positions are what a student sees
 * on their course page.
 */
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Plus } from 'lucide-react';
import { useId, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

function Column({
  title,
  hint,
  items,
  selected,
  onSelect,
  emptyLabel,
  listLabel,
}: {
  title: string;
  hint: string;
  items: string[];
  selected: string | null;
  onSelect: (value: string) => void;
  emptyLabel: string;
  listLabel: string;
}) {
  return (
    <div className="min-w-0 space-y-2">
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-ink-muted">{hint}</p>
      </div>
      <ul
        aria-label={listLabel}
        className="h-56 overflow-y-auto rounded-card border border-line bg-surface p-1"
      >
        {items.length === 0 ? (
          <li className="px-2 py-1.5 text-sm text-ink-faint">{emptyLabel}</li>
        ) : (
          items.map((item) => (
            <li key={item}>
              <button
                type="button"
                aria-pressed={selected === item}
                onClick={() => onSelect(item)}
                className={cn(
                  'w-full truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-sunken',
                  selected === item && 'bg-selected text-selected-fg',
                )}
              >
                {item}
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

export function SubjectPicker({
  pool,
  value,
  onChange,
  className,
}: {
  /** Subjects other courses under this standard use. May be empty. */
  pool: string[];
  value: string[];
  onChange: (next: string[]) => void;
  className?: string;
}) {
  const uid = useId();
  const [typed, setTyped] = useState('');
  const [fromPool, setFromPool] = useState<string | null>(null);
  const [fromCourse, setFromCourse] = useState<string | null>(null);

  const available = pool.filter((item) => !value.includes(item));

  function add(subject: string) {
    const name = subject.trim();
    if (!name || value.includes(name)) return;
    onChange([...value, name]);
  }

  function move(direction: -1 | 1) {
    if (!fromCourse) return;
    const index = value.indexOf(fromCourse);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= value.length) return;
    const next = value.slice();
    const [moved] = next.splice(index, 1);
    next.splice(target, 0, moved!);
    onChange(next);
  }

  return (
    <div className={cn('space-y-3', className)}>
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        <Column
          title="Subjects used elsewhere"
          hint="From other courses under this standard."
          listLabel="Subjects used elsewhere"
          items={available}
          selected={fromPool}
          onSelect={setFromPool}
          emptyLabel="Nothing to borrow — type the subjects below."
        />

        <div className="flex justify-center gap-2 sm:flex-col">
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label="Add the selected subject to this course"
            disabled={!fromPool}
            onClick={() => {
              if (fromPool) add(fromPool);
              setFromPool(null);
            }}
          >
            <ArrowRight className="size-4 sm:block hidden" aria-hidden="true" />
            <ArrowDown className="size-4 sm:hidden" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label="Remove the selected subject from this course"
            disabled={!fromCourse}
            onClick={() => {
              onChange(value.filter((item) => item !== fromCourse));
              setFromCourse(null);
            }}
          >
            <ArrowLeft className="size-4 sm:block hidden" aria-hidden="true" />
            <ArrowUp className="size-4 sm:hidden" aria-hidden="true" />
          </Button>
        </div>

        <div className="space-y-2">
          <Column
            title="Subjects in this course"
            hint="In the order a student will see them."
            listLabel="Subjects in this course"
            items={value}
            selected={fromCourse}
            onSelect={setFromCourse}
            emptyLabel="No subjects yet."
          />
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Move the selected subject up"
              disabled={!fromCourse || value.indexOf(fromCourse) === 0}
              onClick={() => move(-1)}
            >
              <ArrowUp className="size-4" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Move the selected subject down"
              disabled={!fromCourse || value.indexOf(fromCourse) === value.length - 1}
              onClick={() => move(1)}
            >
              <ArrowDown className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      </div>

      <div className="flex items-end gap-2">
        <Field label="Add a subject" htmlFor={`${uid}-typed`} className="flex-1">
          <Input
            id={`${uid}-typed`}
            value={typed}
            placeholder="RHCSA, Python Basics, Interview Preparation…"
            onChange={(event) => setTyped(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== 'Enter') return;
              // Enter adds the subject; without this it submits the whole
              // course form, which is never what typing a subject means.
              event.preventDefault();
              add(typed);
              setTyped('');
            }}
          />
        </Field>
        <Button
          type="button"
          variant="outline"
          className="mb-0.5"
          disabled={!typed.trim()}
          onClick={() => {
            add(typed);
            setTyped('');
          }}
        >
          <Plus className="size-4" aria-hidden="true" />
          Add
        </Button>
      </div>
    </div>
  );
}
