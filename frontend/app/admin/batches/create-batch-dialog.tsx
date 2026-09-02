'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { createBatch } from '@/lib/batches';
import { listCourses } from '@/lib/courses';
import { isoDaysFromNow, isoToday } from '@/lib/batch-labels';
import type { CourseListRow } from '@/types/api';

/**
 * Create a batch.
 *
 * No status or trainer field: a new batch is always upcoming, and assigning a
 * trainer checks their whole timetable, so it has its own step.
 */
export function CreateBatchDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const router = useRouter();
  const [courses, setCourses] = useState<CourseListRow[]>([]);
  const [name, setName] = useState('');
  const [course, setCourse] = useState('');
  const [description, setDescription] = useState('');
  const [startDate, setStartDate] = useState(isoToday());
  const [endDate, setEndDate] = useState(isoDaysFromNow(90));
  const [capacity, setCapacity] = useState('20');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Only published courses can run a batch, so that is what is offered.
    listCourses({ status: 'published', page_size: 100 })
      .then((page) => {
        if (cancelled) return;
        setCourses(page.results);
        if (page.results.length > 0) setCourse(page.results[0]!.id);
      })
      .catch(() => {
        if (!cancelled) setErrors({ __all__: 'Could not load courses.' });
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
      const batch = await createBatch({
        name,
        course,
        description,
        start_date: startDate,
        end_date: endDate,
        capacity: Number(capacity),
      });
      onCreated();
      router.push(`/admin/batches/${batch.id}`);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New batch</CardTitle>
        <CardDescription>
          The batch starts as upcoming. Assign a trainer and a timetable, then activate it.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Batch name" htmlFor="batch-name" error={errors.name} required>
              <Input value={name} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field label="Course" htmlFor="batch-course" error={errors.course} required>
              <Select value={course} onChange={(event) => setCourse(event.target.value)}>
                {courses.length === 0 ? <option value="">No published courses</option> : null}
                {courses.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.title}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Start date" htmlFor="batch-start" error={errors.start_date} required>
              <Input
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </Field>
            <Field label="End date" htmlFor="batch-end" error={errors.end_date} required>
              <Input
                type="date"
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
              />
            </Field>
            <Field
              label="Capacity"
              htmlFor="batch-capacity"
              error={errors.capacity}
              hint="Maximum students holding a seat."
              required
            >
              <Input
                type="number"
                min={1}
                value={capacity}
                onChange={(event) => setCapacity(event.target.value)}
              />
            </Field>
          </div>

          <Field label="Description" htmlFor="batch-description" error={errors.description}>
            <Textarea
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>

          <div className="flex gap-2">
            <Button type="submit" disabled={isSaving || courses.length === 0}>
              {isSaving ? 'Creating…' : 'Create batch'}
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
