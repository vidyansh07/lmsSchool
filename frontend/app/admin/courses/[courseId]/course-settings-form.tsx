'use client';

import { useEffect, useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { listCategories, updateCourse } from '@/lib/courses';
import { DIFFICULTY_OPTIONS, VISIBILITY_OPTIONS } from '@/lib/course-labels';
import type { Category, CourseDetail } from '@/types/api';

/**
 * Course metadata.
 *
 * Status is absent on purpose — it has its own panel, its own endpoint and its
 * own rules. The API rejects it here, naming the field.
 */
export function CourseSettingsForm({
  course,
  onSaved,
}: {
  course: CourseDetail;
  onSaved: () => void | Promise<void>;
}) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [title, setTitle] = useState(course.title);
  const [shortDescription, setShortDescription] = useState(course.short_description);
  const [description, setDescription] = useState(course.description);
  const [category, setCategory] = useState('');
  const [difficulty, setDifficulty] = useState(course.difficulty);
  const [visibility, setVisibility] = useState(course.visibility);
  const [duration, setDuration] = useState(
    course.estimated_duration_minutes ? String(course.estimated_duration_minutes) : '',
  );
  const [objectives, setObjectives] = useState(course.learning_objectives.join('\n'));
  const [prerequisites, setPrerequisites] = useState(course.prerequisites.join('\n'));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listCategories({ page_size: 100 })
      .then((page) => {
        if (cancelled) return;
        setCategories(page.results);
        const current = page.results.find((item) => item.slug === course.category_slug);
        if (current) setCategory(current.id);
      })
      .catch(() => {
        if (!cancelled) setCategories([]);
      });
    return () => {
      cancelled = true;
    };
  }, [course.category_slug]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    setSaved(false);
    try {
      await updateCourse(course.id, {
        title,
        short_description: shortDescription,
        description,
        ...(category ? { category } : {}),
        difficulty,
        visibility,
        estimated_duration_minutes: duration === '' ? null : Number(duration),
        learning_objectives: objectives
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
        prerequisites: prerequisites
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
      });
      setSaved(true);
      await onSaved();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Course details</CardTitle>
        <CardDescription>
          The course code and status are managed elsewhere and cannot be edited here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
          {saved ? <Alert variant="success">Course details saved.</Alert> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Title" htmlFor="edit-title" error={errors.title} required>
              <Input value={title} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field label="Category" htmlFor="edit-category" error={errors.category}>
              <Select value={category} onChange={(event) => setCategory(event.target.value)}>
                {categories.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Difficulty" htmlFor="edit-difficulty" error={errors.difficulty}>
              <Select
                value={difficulty}
                onChange={(event) => setDifficulty(event.target.value as typeof difficulty)}
              >
                {DIFFICULTY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Visibility" htmlFor="edit-visibility" error={errors.visibility}>
              <Select
                value={visibility}
                onChange={(event) => setVisibility(event.target.value as typeof visibility)}
              >
                {VISIBILITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Estimated duration (minutes)"
              htmlFor="edit-duration"
              error={errors.estimated_duration_minutes}
            >
              <Input
                type="number"
                min={0}
                value={duration}
                onChange={(event) => setDuration(event.target.value)}
              />
            </Field>
          </div>

          <Field
            label="Short description"
            htmlFor="edit-short"
            error={errors.short_description}
            hint="One line, shown on catalogue cards."
          >
            <Textarea
              rows={2}
              value={shortDescription}
              onChange={(event) => setShortDescription(event.target.value)}
            />
          </Field>

          <Field label="Full description" htmlFor="edit-description" error={errors.description}>
            <Textarea
              rows={6}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Learning objectives"
              htmlFor="edit-objectives"
              error={errors.learning_objectives}
              hint="One per line, up to 20."
            >
              <Textarea
                rows={5}
                value={objectives}
                onChange={(event) => setObjectives(event.target.value)}
              />
            </Field>
            <Field
              label="Prerequisites"
              htmlFor="edit-prerequisites"
              error={errors.prerequisites}
              hint="One per line."
            >
              <Textarea
                rows={5}
                value={prerequisites}
                onChange={(event) => setPrerequisites(event.target.value)}
              />
            </Field>
          </div>

          <Button type="submit" disabled={isSaving}>
            {isSaving ? 'Saving…' : 'Save details'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
