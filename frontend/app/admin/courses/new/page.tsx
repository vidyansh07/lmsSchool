'use client';

/**
 * New Course, as the reference product asks for it: course information, the
 * subjects it teaches, the fee, and how that fee is collected — one page,
 * one save.
 *
 * A page rather than the dialog this used to be. The dialog asked four
 * questions and left the other half of setting up a course (its subjects, its
 * fee structure) to three more screens, which is how courses ended up priced
 * but empty.
 *
 * What happens on save, in order, and why that order:
 *
 * 1. the course, which is the thing everything else hangs off;
 * 2. its subjects, as modules, in the order shown;
 * 3. its instalment structure, if one was set.
 *
 * Steps 2 and 3 can fail on their own — a subject with an impossible title,
 * a structure that does not add up — and when they do the course still
 * exists. So the screen says what was saved and what was not, and leaves the
 * person on the course it made rather than pretending nothing happened.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';

import { FeeInstalmentEditor, sharesTotal } from '@/components/courses/fee-instalment-editor';
import { SubjectPicker } from '@/components/courses/subject-picker';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { errorMessage, fieldErrors } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { setCourseInstalments, type CourseFeeInstalmentInput } from '@/lib/course-fees';
import { DIFFICULTY_OPTIONS } from '@/lib/course-labels';
import { createCourse, createModule, listCategories, listCourses, listModules } from '@/lib/courses';
import type { Category } from '@/types/api';

/** How many sibling courses to read subjects from. Enough to be useful,
 *  small enough that picking a standard is not a burst of requests. */
const POOL_COURSES = 5;

function NewCourseForm() {
  const router = useRouter();
  const [categories, setCategories] = useState<Category[]>([]);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('');
  const [difficulty, setDifficulty] = useState('beginner');
  const [shortDescription, setShortDescription] = useState('');
  const [defaultFee, setDefaultFee] = useState('');
  const [subjects, setSubjects] = useState<string[]>([]);
  const [borrowed, setBorrowed] = useState<string[]>([]);
  const [instalments, setInstalments] = useState<CourseFeeInstalmentInput[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [partly, setPartly] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void listCategories({ page_size: 100 })
      .then((page) => {
        if (cancelled) return;
        setCategories(page.results);
        setCategory((current) => current || (page.results[0]?.id ?? ''));
      })
      .catch(() => {
        if (!cancelled) setErrors({ __all__: 'Could not load the standards.' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The subject pool follows the standard: subjects already used by other
  // courses under it, so the same subject is spelled the same way everywhere.
  const standardSlug = categories.find((option) => option.id === category)?.slug;
  useEffect(() => {
    if (!standardSlug) return;
    let cancelled = false;
    void listCourses({ category: standardSlug, page_size: POOL_COURSES })
      .then(async (page) => {
        const lists = await Promise.all(
          page.results.map((course) => listModules(course.id).catch(() => [])),
        );
        if (cancelled) return;
        const names = new Set<string>();
        for (const modules of lists) {
          for (const subject of modules) names.add(subject.title);
        }
        setBorrowed([...names].sort((a, b) => a.localeCompare(b)));
      })
      .catch(() => {
        // A pool is a convenience; failing to build it must not stop anybody
        // creating a course, so this is silent and the typed box still works.
        if (!cancelled) setBorrowed([]);
      });
    return () => {
      cancelled = true;
    };
  }, [standardSlug]);

  // Derived, not stored: with no standard picked there is nothing to borrow
  // from, and writing that into state from an effect is the trap the lint
  // rule exists for.
  const pool = standardSlug ? borrowed : [];

  const sharesOk = instalments.length === 0 || Math.abs(sharesTotal(instalments) - 100) < 0.005;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const problems: Record<string, string> = {};
    if (!title.trim()) problems.title = 'Give the course a name.';
    if (!category) problems.category = 'Pick the standard it belongs to.';
    if (!sharesOk) {
      problems.instalments = `The shares add up to ${sharesTotal(instalments).toFixed(2)}%, not 100%.`;
    }
    if (Object.keys(problems).length > 0) {
      setErrors(problems);
      return;
    }

    setSaving(true);
    setErrors({});
    setPartly(null);
    try {
      const course = await createCourse({
        title: title.trim(),
        category,
        difficulty,
        short_description: shortDescription.trim(),
        default_fee: defaultFee.trim() === '' ? null : defaultFee.trim(),
      });

      const leftOut: string[] = [];
      for (const subject of subjects) {
        try {
          await createModule(course.id, { title: subject });
        } catch {
          leftOut.push(subject);
        }
      }
      let structureFailed = '';
      if (instalments.length > 0) {
        try {
          await setCourseInstalments(course.id, instalments);
        } catch (cause) {
          structureFailed = errorMessage(cause);
        }
      }

      if (leftOut.length > 0 || structureFailed) {
        // The course exists. Say exactly what did not make it, on the course
        // itself, rather than losing the rest of the work to one bad row.
        const parts = [
          leftOut.length > 0 ? `these subjects were not added: ${leftOut.join(', ')}` : '',
          structureFailed ? `the instalment structure was not saved (${structureFailed})` : '',
        ].filter(Boolean);
        setPartly(`${course.title} was created, but ${parts.join(', and ')}.`);
        setSaving(false);
        return;
      }

      router.push(`/admin/courses/${course.id}`);
    } catch (cause) {
      setErrors(fieldErrors(cause));
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <Link
        href="/admin/courses"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Courses
      </Link>

      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">New course</h1>
        <p className="text-sm text-ink-muted">
          It starts as a draft: nobody sees it until it is published, and its subjects and fee can
          keep changing until then.
        </p>
      </div>

      {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
      {partly ? <Alert variant="warning">{partly}</Alert> : null}

      {/* No browser validation: a rule the browser enforces refuses the
          submit with nothing on screen explaining why. */}
      <form className="space-y-6" onSubmit={(event) => void submit(event)} noValidate>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Course Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Course Name" htmlFor="course-title" error={errors.title} required>
                <Input
                  id="course-title"
                  autoFocus
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </Field>
              <Field label="Standard" htmlFor="course-category" error={errors.category} required>
                <Select
                  id="course-category"
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                >
                  {categories.length === 0 ? <option value="">No standards yet</option> : null}
                  {categories.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Difficulty" htmlFor="course-difficulty" error={errors.difficulty}>
                <Select
                  id="course-difficulty"
                  value={difficulty}
                  onChange={(event) => setDifficulty(event.target.value)}
                >
                  {DIFFICULTY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field
                label="Course Fees"
                htmlFor="course-fee"
                error={errors.default_fee}
                hint="Offered as the default when a student registers; a counsellor can change it per student."
              >
                <Input
                  id="course-fee"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="1"
                  value={defaultFee}
                  placeholder="e.g. 25000"
                  onChange={(event) => setDefaultFee(event.target.value)}
                />
              </Field>
            </div>
            <Field
              label="Short description"
              htmlFor="course-short"
              error={errors.short_description}
              hint="One line, shown on catalogue cards."
            >
              <Textarea
                id="course-short"
                rows={2}
                value={shortDescription}
                onChange={(event) => setShortDescription(event.target.value)}
              />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Subjects</CardTitle>
          </CardHeader>
          <CardContent>
            <SubjectPicker pool={pool} value={subjects} onChange={setSubjects} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Fee Instalment Structure</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-ink-muted">
              How this fee is normally collected, so a counsellor does not retype it at every
              admission. Shares are of what each student actually pays, so a discount scales them.
            </p>
            <FeeInstalmentEditor rows={instalments} onChange={setInstalments} errors={errors} />
          </CardContent>
        </Card>

        <div className="flex gap-2">
          <Button type="submit" disabled={saving || categories.length === 0}>
            {saving ? 'Creating…' : 'Create course'}
          </Button>
          <Button type="button" variant="ghost" asChild>
            <Link href="/admin/courses">Cancel</Link>
          </Button>
        </div>
      </form>
    </div>
  );
}

export default function NewCoursePage() {
  return (
    <RequireAuth capability={Capability.courseCreate}>
      <NewCourseForm />
    </RequireAuth>
  );
}
