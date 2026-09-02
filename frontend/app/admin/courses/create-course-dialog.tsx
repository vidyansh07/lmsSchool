'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { createCourse, listCategories } from '@/lib/courses';
import { DIFFICULTY_OPTIONS } from '@/lib/course-labels';
import type { Category } from '@/types/api';

/**
 * Create a course.
 *
 * No status field: a new course is always a draft, and publishing has its own
 * gated endpoint. The API would reject `status` here anyway, naming the field.
 */
export function CreateCourseDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const router = useRouter();
  const [categories, setCategories] = useState<Category[]>([]);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('');
  const [shortDescription, setShortDescription] = useState('');
  const [difficulty, setDifficulty] = useState('beginner');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listCategories({ page_size: 100 })
      .then((page) => {
        if (cancelled) return;
        setCategories(page.results);
        if (page.results.length > 0) setCategory(page.results[0]!.id);
      })
      .catch(() => {
        if (!cancelled) setErrors({ __all__: 'Could not load categories.' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    try {
      const course = await createCourse({
        title,
        category,
        short_description: shortDescription,
        difficulty,
      });
      onCreated();
      router.push(`/admin/courses/${course.id}`);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New course</CardTitle>
        <CardDescription>
          The course starts as a draft. Add modules and lessons, then publish it.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Title" htmlFor="course-title" error={errors.title} required>
              <Input value={title} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <Field label="Category" htmlFor="course-category" error={errors.category} required>
              <Select value={category} onChange={(event) => setCategory(event.target.value)}>
                {categories.length === 0 ? <option value="">No categories yet</option> : null}
                {categories.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Difficulty" htmlFor="course-difficulty" error={errors.difficulty}>
              <Select value={difficulty} onChange={(event) => setDifficulty(event.target.value)}>
                {DIFFICULTY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field
            label="Short description"
            htmlFor="course-short"
            error={errors.short_description}
            hint="One line, shown on catalogue cards."
          >
            <Textarea
              rows={2}
              value={shortDescription}
              onChange={(event) => setShortDescription(event.target.value)}
            />
          </Field>

          <div className="flex gap-2">
            <Button type="submit" disabled={isSaving || categories.length === 0}>
              {isSaving ? 'Creating…' : 'Create course'}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
