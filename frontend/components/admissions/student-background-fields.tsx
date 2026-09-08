'use client';

/**
 * Who is being registered: a college student, or a working professional.
 *
 * The owner asked for the two to be handled differently at the desk, and
 * they are different conversations. A college student is asked which college
 * and when they finish; a professional is asked where they work and what
 * they do there — the first things a corporate-training or referral
 * conversation needs. One control chooses, and only the relevant questions
 * follow it, so a counsellor is never asked for a graduation year from
 * somebody with a job.
 *
 * The choice is three real radio buttons drawn as cards: keyboard-operable,
 * announced as a group, and "Not sure yet" is a first-class answer rather
 * than an absence — a walk-in who has not said is not the same as one who
 * has said "neither".
 */

import { Briefcase, GraduationCap, HelpCircle, type LucideIcon } from 'lucide-react';

import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { InstitutionKind } from '@/types/api';

export interface StudentBackground {
  kind: InstitutionKind | '';
  institution: string;
  graduationYear: string;
  jobTitle: string;
}

export const EMPTY_BACKGROUND: StudentBackground = {
  kind: '',
  institution: '',
  graduationYear: '',
  jobTitle: '',
};

const OPTIONS: { value: InstitutionKind | ''; label: string; hint: string; icon: LucideIcon }[] = [
  {
    value: 'college',
    label: 'College student',
    hint: 'Studying now, learning alongside a degree',
    icon: GraduationCap,
  },
  {
    value: 'employer',
    label: 'Working professional',
    hint: 'In a job, here to add a skill',
    icon: Briefcase,
  },
  { value: '', label: 'Not sure yet', hint: 'Ask later', icon: HelpCircle },
];

/** The current year, for the graduation-year bounds. */
const THIS_YEAR = new Date().getFullYear();

/**
 * What the wizard sends for `profile`. Fields that do not apply to the chosen
 * kind are sent empty on purpose, so switching from "working" to "college"
 * does not leave a stale designation on the record.
 */
export function backgroundToProfile(background: StudentBackground): {
  institution: string;
  institution_kind: InstitutionKind | '';
  job_title: string;
  graduation_year: number | null;
} {
  const year = Number.parseInt(background.graduationYear, 10);
  return {
    institution: background.institution.trim(),
    institution_kind: background.kind,
    job_title: background.kind === 'employer' ? background.jobTitle.trim() : '',
    graduation_year: background.kind === 'college' && Number.isFinite(year) ? year : null,
  };
}

/** One line for the confirm step: "Infosys — Senior Engineer", "JECRC (2027)". */
export function describeBackground(background: StudentBackground): string {
  const name = background.institution.trim();
  if (background.kind === 'employer') {
    const title = background.jobTitle.trim();
    if (!name && !title) return 'Working professional';
    return [name, title].filter(Boolean).join(' — ');
  }
  if (background.kind === 'college') {
    const year = background.graduationYear.trim();
    if (!name && !year) return 'College student';
    return year ? `${name || 'College'} (${year})` : name;
  }
  return 'Not specified';
}

export function StudentBackgroundFields({
  value,
  onChange,
  errors = {},
  idPrefix,
}: {
  value: StudentBackground;
  onChange: (next: StudentBackground) => void;
  errors?: Record<string, string>;
  /** Keeps ids unique when two forms are on one page. */
  idPrefix: string;
}) {
  const set = (patch: Partial<StudentBackground>) => onChange({ ...value, ...patch });

  return (
    <fieldset className="space-y-3">
      <legend className="text-sm font-medium">Who is registering?</legend>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Who is registering">
        {OPTIONS.map((option) => {
          const Icon = option.icon;
          const checked = value.kind === option.value;
          const id = `${idPrefix}-kind-${option.value || 'unknown'}`;
          return (
            <label
              key={option.value || 'unknown'}
              htmlFor={id}
              className={cn(
                'press flex cursor-pointer items-start gap-3 rounded-[var(--radius-card)] border p-3 transition-colors duration-[var(--duration-quick)]',
                'has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary',
                checked
                  ? 'border-primary bg-accent'
                  : 'border-border bg-surface hover:border-primary/40 hover:bg-muted',
              )}
            >
              <input
                id={id}
                type="radio"
                name={`${idPrefix}-kind`}
                value={option.value}
                checked={checked}
                onChange={() => set({ kind: option.value })}
                className="sr-only"
              />
              <span
                className={cn(
                  'flex size-9 shrink-0 items-center justify-center rounded-xl',
                  checked ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
                )}
              >
                <Icon className="size-[18px]" strokeWidth={1.75} aria-hidden="true" />
              </span>
              <span className="min-w-0 leading-tight">
                <span className={cn('block text-sm font-semibold', checked ? 'text-primary' : 'text-foreground')}>
                  {option.label}
                </span>
                <span className="block text-xs text-muted-foreground">{option.hint}</span>
              </span>
            </label>
          );
        })}
      </div>

      {value.kind === 'college' ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="College name" htmlFor={`${idPrefix}-institution`} error={errors.institution}>
            <Input
              id={`${idPrefix}-institution`}
              value={value.institution}
              onChange={(event) => set({ institution: event.target.value })}
              placeholder="e.g. JECRC University"
            />
          </Field>
          <Field
            label="Expected graduation year"
            htmlFor={`${idPrefix}-graduation-year`}
            error={errors.graduation_year}
            hint="Leave blank if unknown."
          >
            <Input
              id={`${idPrefix}-graduation-year`}
              type="number"
              inputMode="numeric"
              min={THIS_YEAR - 10}
              max={THIS_YEAR + 8}
              step="1"
              value={value.graduationYear}
              onChange={(event) => set({ graduationYear: event.target.value })}
              placeholder={String(THIS_YEAR + 1)}
            />
          </Field>
        </div>
      ) : null}

      {value.kind === 'employer' ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Company name" htmlFor={`${idPrefix}-institution`} error={errors.institution}>
            <Input
              id={`${idPrefix}-institution`}
              value={value.institution}
              onChange={(event) => set({ institution: event.target.value })}
              placeholder="e.g. Infosys"
            />
          </Field>
          <Field label="Designation" htmlFor={`${idPrefix}-job-title`} error={errors.job_title}>
            <Input
              id={`${idPrefix}-job-title`}
              value={value.jobTitle}
              onChange={(event) => set({ jobTitle: event.target.value })}
              placeholder="e.g. Senior Systems Engineer"
            />
          </Field>
        </div>
      ) : null}
    </fieldset>
  );
}
