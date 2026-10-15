'use client';

/**
 * A list of short labels — a trainer's skills — typed one at a time.
 *
 * Enter or a comma adds what was typed; Backspace in an empty box removes the
 * last one; each chip has its own remove button with an accessible name. A
 * duplicate (ignoring case) is not added twice, and the limits match the
 * server's (`apps/trainers/models.py`: 30 skills, 50 characters each), so a
 * list this control produced is never refused for its shape.
 */

import { useState } from 'react';
import { X } from 'lucide-react';

import { cn } from '@/lib/utils';

export function TagInput({
  id,
  value,
  onChange,
  placeholder,
  maxTags = 30,
  maxLength = 50,
  disabled = false,
  'aria-describedby': describedBy,
}: {
  id: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  maxTags?: number;
  maxLength?: number;
  disabled?: boolean;
  'aria-describedby'?: string;
}) {
  const [draft, setDraft] = useState('');
  const full = value.length >= maxTags;

  function add(raw: string) {
    const parts = raw
      .split(',')
      .map((part) => part.trim().slice(0, maxLength))
      .filter(Boolean);
    if (parts.length === 0) return;
    const next = [...value];
    for (const part of parts) {
      if (next.length >= maxTags) break;
      if (!next.some((existing) => existing.toLowerCase() === part.toLowerCase())) next.push(part);
    }
    onChange(next);
    setDraft('');
  }

  return (
    <div
      className={cn(
        'flex min-h-10 flex-wrap items-center gap-1.5 rounded-control border border-line bg-surface px-2 py-1.5',
        'focus-within:ring-2 focus-within:ring-action/40',
        disabled && 'opacity-60',
      )}
    >
      {value.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-full bg-sunken px-2 py-0.5 text-xs font-medium"
        >
          {tag}
          <button
            type="button"
            disabled={disabled}
            className="rounded-full p-0.5 text-ink-muted hover:text-ink"
            aria-label={`Remove ${tag}`}
            onClick={() => onChange(value.filter((existing) => existing !== tag))}
          >
            <X className="size-3" aria-hidden="true" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        disabled={disabled || full}
        maxLength={maxLength * 4}
        aria-describedby={describedBy}
        placeholder={full ? `Up to ${maxTags}` : placeholder}
        className="min-w-[8rem] flex-1 bg-transparent text-sm outline-none placeholder:text-ink-muted"
        onChange={(event) => {
          const next = event.target.value;
          if (next.includes(',')) add(next);
          else setDraft(next);
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            add(draft);
          } else if (event.key === 'Backspace' && draft === '' && value.length > 0) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={() => add(draft)}
      />
    </div>
  );
}
