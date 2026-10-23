'use client';

/**
 * Guardian Details — step 2 of the admissions wizard.
 *
 * One block per guardian, added and removed as a set, because that is how the
 * form is read and how the server stores it: what was sent is what there is.
 *
 * The "First guardian" tick is the one the message settings mean by "First
 * Guardian of the student" — the person the institute rings when it rings one
 * rather than all. It behaves as a radio however many boxes are drawn: two
 * first guardians is not a state that means anything, and the server picks
 * the first row if nobody ticks one.
 *
 * Guardians are optional. An adult student paying their own fee has none, and
 * a step that could not be skipped would have the desk inventing one.
 */

import { useRouter } from 'next/navigation';
import { use, useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import { AddAnother, FormRow } from '@/components/classpro/form-row';
import { StepBar, type WizardStep } from '@/components/classpro/step-bar';
import { Tips } from '@/components/classpro/tips';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/input';
import { LoadingState } from '@/components/states';
import { fieldErrors, unshownError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import {
  GUARDIAN_RELATIONS,
  GUARDIAN_RELATION_LABEL,
  listGuardians,
  setGuardians,
  type GuardianInput,
} from '@/lib/guardians';

const STEPS: WizardStep[] = [
  { key: 'student', label: 'Student Details' },
  { key: 'guardian', label: 'Guardian Details' },
  { key: 'admission', label: 'Admission Details' },
  { key: 'payment', label: 'Payment Details' },
  { key: 'batch', label: 'Batch Details' },
];

interface Row extends GuardianInput {
  key: string;
}

let counter = 0;
function blankRow(): Row {
  counter += 1;
  return {
    key: `guardian-${counter}`,
    name: '',
    relation: 'father',
    mobile: '',
    email: '',
    occupation: '',
  };
}

export function GuardianDetailsForm({ studentId }: { studentId: string }) {
  const router = useRouter();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [primary, setPrimary] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listGuardians(studentId)
      .then((found) => {
        if (cancelled) return;
        if (found.length === 0) {
          setRows([blankRow()]);
          return;
        }
        setRows(
          found.map((guardian) => ({
            key: guardian.id,
            name: guardian.name,
            relation: guardian.relation,
            mobile: guardian.mobile,
            email: guardian.email,
            occupation: guardian.occupation,
          })),
        );
        const marked = found.findIndex((guardian) => guardian.is_primary);
        setPrimary(marked === -1 ? 0 : marked);
      })
      .catch(() => {
        // A student with no guardians yet reads as an empty list; anything
        // else failing still leaves a usable form rather than a dead screen.
        if (!cancelled) setRows([blankRow()]);
      });
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  function update(key: string, patch: Partial<Row>) {
    setRows((current) =>
      (current ?? []).map((row) => (row.key === key ? { ...row, ...patch } : row)),
    );
  }

  function remove(index: number) {
    setRows((current) => {
      const next = (current ?? []).filter((_, position) => position !== index);
      return next.length === 0 ? [blankRow()] : next;
    });
    setPrimary((current) => {
      if (index === current) return 0;
      return index < current ? current - 1 : current;
    });
  }

  async function save(andContinue: boolean) {
    const filled = (rows ?? []).filter((row) => row.name.trim());
    if (filled.some((row) => !row.name.trim())) {
      setErrors({ guardians: 'Every guardian needs a name.' });
      return;
    }
    setSaving(true);
    setErrors({});
    try {
      await setGuardians(
        studentId,
        filled.map((row, index) => ({
          name: row.name.trim(),
          relation: row.relation,
          mobile: (row.mobile ?? '').trim(),
          email: (row.email ?? '').trim(),
          occupation: (row.occupation ?? '').trim(),
          is_primary: index === Math.min(primary, Math.max(filled.length - 1, 0)),
        })),
      );
      if (andContinue) router.push(`/students/${studentId}/admissions/new`);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  const stray = unshownError(errors, ['guardians', 'name', 'mobile', 'email']);

  if (rows === null) return <LoadingState label="Loading guardians…" rows={4} />;

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-card border border-line bg-surface">
        <StepBar
          steps={STEPS}
          current="guardian"
          furthest="guardian"
          onSelect={(key) => {
            if (key === 'student') router.push(`/students/${studentId}`);
          }}
          onPrevious={() => router.push(`/students/${studentId}`)}
          onNext={() => void save(true)}
        />

        <div className="grid gap-8 p-5 lg:grid-cols-[minmax(0,1fr)_16rem]">
          <form
            className="min-w-0 space-y-6"
            onSubmit={(event) => {
              event.preventDefault();
              void save(true);
            }}
          >
            {stray ? <Alert variant="error">{stray}</Alert> : null}
            {errors.guardians ? <Alert variant="error">{errors.guardians}</Alert> : null}

            {rows.map((row, index) => (
              <fieldset
                key={row.key}
                className="space-y-1 rounded-card border border-line p-4"
              >
                <legend className="px-1 text-sm font-semibold text-ink">
                  Guardian {index + 1}
                </legend>

                <FormRow label="Name" htmlFor={`${row.key}-name`} required>
                  <Input
                    id={`${row.key}-name`}
                    value={row.name}
                    onChange={(event) => update(row.key, { name: event.target.value })}
                    placeholder="Full name"
                  />
                </FormRow>

                <FormRow label="Relation" htmlFor={`${row.key}-relation`}>
                  <Select
                    id={`${row.key}-relation`}
                    value={row.relation}
                    onChange={(event) =>
                      update(row.key, { relation: event.target.value as Row['relation'] })
                    }
                    className="max-w-xs"
                  >
                    {GUARDIAN_RELATIONS.map((value) => (
                      <option key={value} value={value}>
                        {GUARDIAN_RELATION_LABEL[value]}
                      </option>
                    ))}
                  </Select>
                </FormRow>

                <FormRow label="Mobile" htmlFor={`${row.key}-mobile`}>
                  <Input
                    id={`${row.key}-mobile`}
                    value={row.mobile}
                    onChange={(event) => update(row.key, { mobile: event.target.value })}
                  />
                </FormRow>

                <FormRow label="Email" htmlFor={`${row.key}-email`}>
                  <Input
                    id={`${row.key}-email`}
                    type="email"
                    value={row.email}
                    onChange={(event) => update(row.key, { email: event.target.value })}
                  />
                </FormRow>

                <FormRow label="Occupation" htmlFor={`${row.key}-occupation`}>
                  <Input
                    id={`${row.key}-occupation`}
                    value={row.occupation}
                    onChange={(event) => update(row.key, { occupation: event.target.value })}
                  />
                </FormRow>

                <FormRow label="First guardian">
                  <div className="flex items-center justify-between gap-3">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="radio"
                        name="primary-guardian"
                        checked={primary === index}
                        onChange={() => setPrimary(index)}
                        className="size-4 accent-[var(--color-action)]"
                      />
                      Ring this one first
                    </label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove guardian ${index + 1}`}
                      onClick={() => remove(index)}
                    >
                      <Trash2 className="size-4 text-action" aria-hidden="true" />
                    </Button>
                  </div>
                </FormRow>
              </fieldset>
            ))}

            <AddAnother onClick={() => setRows([...(rows ?? []), blankRow()])}>
              <span className="inline-flex items-center gap-1">
                <Plus className="size-3.5" aria-hidden="true" />
                Add another guardian
              </span>
            </AddAnother>

            <div className="flex flex-wrap gap-2 pt-2">
              <Button type="submit" disabled={saving} className="bg-success hover:bg-success/90">
                {saving ? 'Saving…' : 'Save and continue'}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={saving}
                onClick={() => router.push(`/students/${studentId}/admissions/new`)}
              >
                Skip
              </Button>
            </div>
          </form>

          <Tips>
            <p>
              The <strong className="text-ink">first guardian</strong> is the one the institute
              rings when it rings one rather than all — fee reminders, attendance, exam results.
            </p>
            <p>
              A student paying their own fee needs none of this. Skip it; nothing later depends
              on a guardian existing.
            </p>
          </Tips>
        </div>
      </div>
    </div>
  );
}

export default function GuardianDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth capability={Capability.studentCreate}>
      <GuardianDetailsForm studentId={id} />
    </RequireAuth>
  );
}
