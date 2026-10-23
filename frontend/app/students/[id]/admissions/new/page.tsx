'use client';

/**
 * Admission Details — step 3 of the admissions wizard, and the screen the
 * money starts on.
 *
 * It is one table: a row per thing being charged for, with the academic year,
 * the course, how many, and the fee. "+ Course" adds a course row;
 * "+ Additional Fee" adds a named charge beside one (an exam fee, a kit).
 * Underneath, the three figures that follow from the rows — what the lines
 * come to, the discount if there is one, and the total — and a note.
 *
 * Two things worth knowing about what this sends:
 *
 * * **The fee is a snapshot.** Choosing a course fills in its price today and
 *   then stops tracking it: a price change next March must never move what
 *   this student was charged. The server freezes it the same way.
 * * **The discount belongs to the admission**, not to a course. The server
 *   splits it across the course lines pro-rata so the parts add back to
 *   exactly the whole — the arithmetic is deliberately not done here, because
 *   a screen that redoes a sum can disagree with the ledger it is reporting.
 *
 * An additional fee is charged *on* a course line — it has to be, because a
 * course is what has an enrolment and an enrolment is what has a fee plan.
 * The row says which, defaulting to the first course.
 */

import { useRouter } from 'next/navigation';
import { use, useEffect, useMemo, useState } from 'react';
import { Minus, Plus, Trash2 } from 'lucide-react';

import { StepBar, type WizardStep } from '@/components/classpro/step-bar';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input, Select, Textarea } from '@/components/ui/input';
import { LoadingState } from '@/components/states';
import { fieldErrors, unshownError } from '@/lib/api';
import { listAcademicYears, type AcademicYear } from '@/lib/academic-years';
import { createAdmission, type AdmissionLineInput, type DiscountKind } from '@/lib/admissions-api';
import { Capability } from '@/lib/capabilities';
import { listCourses } from '@/lib/courses';
import { formatDate, localIsoDate } from '@/lib/format';
import type { CourseListRow } from '@/types/api';

const STEPS: WizardStep[] = [
  { key: 'student', label: 'Student Details' },
  { key: 'guardian', label: 'Guardian Details' },
  { key: 'admission', label: 'Admission Details' },
  { key: 'payment', label: 'Payment Details' },
  { key: 'batch', label: 'Batch Details' },
];

interface Row {
  key: string;
  kind: 'course' | 'additional_fee';
  course: string;
  label: string;
  quantity: number;
  fee: string;
  /** For an additional fee: the key of the course row it is charged on. */
  chargedOn: string;
}

let counter = 0;
function blankRow(kind: Row['kind']): Row {
  counter += 1;
  return {
    key: `line-${counter}`,
    kind,
    course: '',
    label: '',
    quantity: 1,
    fee: '',
    chargedOn: '',
  };
}

/** Rupees as the screens write them: "Rs. 30,000". Not `formatCurrency`,
 *  which writes the ₹ symbol — these screens say "Rs." throughout and the two
 *  must not appear on one page. */
export function rupees(value: number): string {
  return `Rs. ${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

function toNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function AdmissionDetailsForm({ studentId }: { studentId: string }) {
  const router = useRouter();
  const [years, setYears] = useState<AcademicYear[]>([]);
  const [courses, setCourses] = useState<CourseListRow[]>([]);
  const [loading, setLoading] = useState(true);

  const [admissionDate, setAdmissionDate] = useState(() => localIsoDate());
  const [year, setYear] = useState('');
  const [rows, setRows] = useState<Row[]>([blankRow('course')]);
  const [discountKind, setDiscountKind] = useState<DiscountKind>('flat');
  const [discountValue, setDiscountValue] = useState('0');
  const [note, setNote] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listAcademicYears(), listCourses({ page_size: 200, status: 'published' })])
      .then(([yearRows, coursePage]) => {
        if (cancelled) return;
        setYears(yearRows);
        setCourses(coursePage.results);
        setYear(yearRows.find((row) => row.is_current)?.id ?? yearRows[0]?.id ?? '');
      })
      .catch(() => {
        // The form still works with an empty catalogue: the counsellor sees
        // "no courses" rather than a blank screen, and nothing is lost.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** The course list grouped under its category — "standard", in the words
   *  the catalogue screens use. */
  const grouped = useMemo(() => {
    const groups = new Map<string, CourseListRow[]>();
    for (const course of courses) {
      const key = course.category_name || 'Other';
      groups.set(key, [...(groups.get(key) ?? []), course]);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [courses]);

  const courseRows = rows.filter((row) => row.kind === 'course');
  const grossTotal = rows.reduce((sum, row) => sum + toNumber(row.fee) * row.quantity, 0);
  const discount =
    discountKind === 'percent'
      ? (grossTotal * Math.min(toNumber(discountValue), 100)) / 100
      : Math.min(toNumber(discountValue), grossTotal);
  const totalFees = Math.max(grossTotal - discount, 0);

  function update(key: string, patch: Partial<Row>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function remove(key: string) {
    setRows((current) => {
      const next = current.filter((row) => row.key !== key);
      // An additional fee charged on a course that has gone is charged on
      // nothing, so it goes with it rather than becoming an orphan.
      const courseKeys = new Set(next.filter((r) => r.kind === 'course').map((r) => r.key));
      const kept = next.filter((row) => row.kind === 'course' || courseKeys.has(row.chargedOn));
      return kept.length === 0 ? [blankRow('course')] : kept;
    });
  }

  function addCourse() {
    setRows((current) => [...current, blankRow('course')]);
  }

  function addAdditionalFee() {
    setRows((current) => {
      const firstCourse = current.find((row) => row.kind === 'course');
      if (!firstCourse) return current;
      return [...current, { ...blankRow('additional_fee'), chargedOn: firstCourse.key }];
    });
  }

  function onCourseChosen(key: string, courseId: string) {
    const chosen = courses.find((course) => course.id === courseId);
    update(key, { course: courseId, fee: chosen?.default_fee ?? '' });
  }

  function validate(): Record<string, string> {
    const found: Record<string, string> = {};
    if (courseRows.length === 0) found.lines = 'An admission needs at least one course.';
    if (courseRows.some((row) => !row.course)) found.lines = 'Choose the course on every line.';
    if (rows.some((row) => row.kind === 'additional_fee' && !row.label.trim())) {
      found.lines = 'Name every additional fee.';
    }
    if (!admissionDate) found.admission_date = 'Give the admission date.';
    if (discountKind === 'percent' && toNumber(discountValue) > 100) {
      found.discount = 'A discount cannot be more than 100%.';
    }
    return found;
  }

  async function save() {
    const found = validate();
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }
    setSaving(true);
    setErrors({});

    const order = rows.map((row) => row.key);
    const lines: AdmissionLineInput[] = rows.map((row) =>
      row.kind === 'course'
        ? {
            kind: 'course',
            course: row.course,
            quantity: row.quantity,
            unit_fee: row.fee || '0',
          }
        : {
            kind: 'additional_fee',
            label: row.label.trim(),
            quantity: row.quantity,
            unit_fee: row.fee || '0',
            charged_on: order.indexOf(row.chargedOn),
          },
    );

    try {
      const admission = await createAdmission({
        student: studentId,
        academic_year: year || null,
        admission_date: admissionDate,
        discount_kind: discountKind,
        discount_value: String(toNumber(discountValue)),
        note,
        lines,
      });
      router.push(`/students/${studentId}/admissions/${admission.id}/payment`);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  const stray = unshownError(errors, ['lines', 'admission_date', 'discount', 'course', 'label']);

  if (loading) return <LoadingState label="Loading courses…" rows={6} />;

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-card border border-line bg-surface">
        <StepBar
          steps={STEPS}
          current="admission"
          furthest="admission"
          onSelect={(key) => {
            if (key === 'student') router.push(`/students/${studentId}`);
          }}
          onPrevious={() => router.push(`/students/${studentId}/guardians`)}
          onNext={() => void save()}
        />

        <div className="space-y-6 p-5">
          {stray ? <Alert variant="error">{stray}</Alert> : null}

          <section className="space-y-3">
            <h2 className="text-lg font-normal text-ink">Basic Information</h2>
            <div className="grid gap-1.5 sm:grid-cols-[9rem_1fr] sm:gap-4">
              <label
                htmlFor="admission-date"
                className="pt-2 text-sm font-semibold text-ink sm:text-right"
              >
                Admission Date
              </label>
              <div className="max-w-xs space-y-1.5">
                <Input
                  id="admission-date"
                  type="date"
                  value={admissionDate}
                  onChange={(event) => setAdmissionDate(event.target.value)}
                />
                {errors.admission_date ? (
                  <p className="text-xs text-danger" role="alert">
                    {errors.admission_date}
                  </p>
                ) : null}
                <p className="text-xs text-ink-muted">{formatDate(admissionDate)}</p>
              </div>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-normal text-ink">Course Information</h2>

            <div className="space-y-4 rounded-card bg-sunken/50 p-4">
              <div className="hidden gap-4 px-1 text-sm font-semibold text-ink md:grid md:grid-cols-[10rem_minmax(0,1fr)_9rem_12rem_2.5rem]">
                <span>Academic Year</span>
                <span>Course</span>
                <span>Qty</span>
                <span>Fees</span>
                <span className="sr-only">Remove</span>
              </div>

              <ul className="space-y-3">
                {rows.map((row, index) => (
                  <li
                    key={row.key}
                    className="grid gap-3 md:grid-cols-[10rem_minmax(0,1fr)_9rem_12rem_2.5rem] md:items-start"
                  >
                    <div>
                      {index === 0 ? (
                        <Select
                          aria-label="Academic Year"
                          value={year}
                          onChange={(event) => setYear(event.target.value)}
                        >
                          {years.length === 0 ? <option value="">No year</option> : null}
                          {years.map((option) => (
                            <option key={option.id} value={option.id} disabled={option.is_closed}>
                              {option.name}
                              {option.is_closed ? ' (closed)' : ''}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <span className="hidden md:block" aria-hidden="true" />
                      )}
                    </div>

                    {row.kind === 'course' ? (
                      <Select
                        aria-label={`Course ${index + 1}`}
                        value={row.course}
                        onChange={(event) => onCourseChosen(row.key, event.target.value)}
                      >
                        <option value="">Select Course</option>
                        {grouped.map(([group, items]) => (
                          <optgroup key={group} label={group}>
                            {items.map((course) => (
                              <option key={course.id} value={course.id}>
                                {course.title}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </Select>
                    ) : (
                      <div className="space-y-2">
                        <Input
                          aria-label={`Additional fee ${index + 1}`}
                          value={row.label}
                          onChange={(event) => update(row.key, { label: event.target.value })}
                          placeholder="Name the fee — exam fee, kit"
                        />
                        <Select
                          aria-label={`Charged on ${index + 1}`}
                          value={row.chargedOn}
                          onChange={(event) => update(row.key, { chargedOn: event.target.value })}
                        >
                          {courseRows.map((courseRow, position) => (
                            <option key={courseRow.key} value={courseRow.key}>
                              Charged on:{' '}
                              {courses.find((c) => c.id === courseRow.course)?.title ??
                                `course ${position + 1}`}
                            </option>
                          ))}
                        </Select>
                      </div>
                    )}

                    <div className="flex items-center gap-1">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        aria-label={`One fewer on line ${index + 1}`}
                        onClick={() => update(row.key, { quantity: Math.max(1, row.quantity - 1) })}
                      >
                        <Minus className="size-3.5" aria-hidden="true" />
                      </Button>
                      <Input
                        aria-label={`Qty ${index + 1}`}
                        type="number"
                        min={1}
                        value={String(row.quantity)}
                        onChange={(event) =>
                          update(row.key, { quantity: Math.max(1, Number(event.target.value) || 1) })
                        }
                        className="w-14 text-center"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        aria-label={`One more on line ${index + 1}`}
                        onClick={() => update(row.key, { quantity: row.quantity + 1 })}
                      >
                        <Plus className="size-3.5" aria-hidden="true" />
                      </Button>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="shrink-0 rounded-control border border-line bg-surface px-2.5 py-2 text-sm text-ink-muted">
                        Rs.
                      </span>
                      <Input
                        aria-label={`Fees ${index + 1}`}
                        type="number"
                        min={0}
                        step="100"
                        value={row.fee}
                        onChange={(event) => update(row.key, { fee: event.target.value })}
                        placeholder="0.0"
                      />
                    </div>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove line ${index + 1}`}
                      onClick={() => remove(row.key)}
                    >
                      <Trash2 className="size-4 text-action" aria-hidden="true" />
                    </Button>
                  </li>
                ))}
              </ul>

              {errors.lines ? (
                <p className="text-xs text-danger" role="alert">
                  {errors.lines}
                </p>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" onClick={addCourse}>
                  <Plus className="size-3.5" aria-hidden="true" />
                  Course
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addAdditionalFee}
                  disabled={courseRows.length === 0}
                >
                  <Plus className="size-3.5" aria-hidden="true" />
                  Additional Fee
                </Button>
              </div>

              <dl className="ml-auto max-w-xl space-y-2 pt-2">
                <SummaryRow label="Fees">
                  <span className="tabular-nums" data-testid="gross-total">
                    {rupees(grossTotal)}
                  </span>
                </SummaryRow>
                <SummaryRow label="Discount if any?">
                  <div className="flex items-center gap-2">
                    <span className="shrink-0 rounded-control border border-line bg-surface px-2.5 py-2 text-sm text-ink-muted">
                      Rs.
                    </span>
                    <Input
                      aria-label="Discount"
                      type="number"
                      min={0}
                      value={discountValue}
                      onChange={(event) => setDiscountValue(event.target.value)}
                    />
                    <Select
                      aria-label="Discount kind"
                      value={discountKind}
                      onChange={(event) => setDiscountKind(event.target.value as DiscountKind)}
                      className="w-28 shrink-0"
                    >
                      <option value="flat">Flat</option>
                      <option value="percent">Percent</option>
                    </Select>
                  </div>
                </SummaryRow>
                {errors.discount ? (
                  <p className="text-right text-xs text-danger" role="alert">
                    {errors.discount}
                  </p>
                ) : null}
                <SummaryRow label="Total Fees">
                  <span className="font-semibold tabular-nums" data-testid="total-fees">
                    {rupees(totalFees)}
                  </span>
                </SummaryRow>
                <SummaryRow label="Note">
                  <Textarea
                    aria-label="Note"
                    rows={3}
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                  />
                </SummaryRow>
              </dl>
            </div>
          </section>

          <div className="flex gap-2">
            <Button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="bg-success hover:bg-success/90"
            >
              {saving ? 'Saving…' : 'Save'}
            </Button>
            <Button type="button" variant="outline" onClick={() => router.push(`/students/${studentId}`)}>
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** One line of the figures under the table: a grey label pill on the left,
 *  the figure or control on the right — the shape the original draws. */
function SummaryRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_minmax(0,1fr)] items-center gap-3">
      <dt className="rounded-control bg-ink-muted/15 px-3 py-1.5 text-center text-xs font-semibold text-ink">
        {label}
      </dt>
      <dd>{children}</dd>
    </div>
  );
}

export default function NewAdmissionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth capability={Capability.enrolmentCreate}>
      <AdmissionDetailsForm studentId={id} />
    </RequireAuth>
  );
}
