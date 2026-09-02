import Link from 'next/link';
import { BookOpen, Clock, Layers } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DIFFICULTY_LABEL, STATUS_LABEL, STATUS_VARIANT, formatDuration } from '@/lib/course-labels';
import type { CourseListRow } from '@/types/api';

/**
 * One catalogue row. Reused by the student catalogue and both admin lists, so
 * a course looks the same wherever it appears.
 */
export function CourseCard({
  course,
  href,
  showStatus = false,
}: {
  course: CourseListRow;
  href: string;
  showStatus?: boolean;
}) {
  return (
    <Card className="flex h-full flex-col transition-colors hover:border-primary">
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{course.category_name}</Badge>
          <Badge>{DIFFICULTY_LABEL[course.difficulty]}</Badge>
          {showStatus ? (
            <Badge variant={STATUS_VARIANT[course.status]}>{STATUS_LABEL[course.status]}</Badge>
          ) : null}
        </div>
        <CardTitle>
          <Link href={href} className="hover:text-primary">
            {course.title}
          </Link>
        </CardTitle>
        <p className="font-mono text-xs text-muted-foreground">{course.code}</p>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {course.short_description || 'No description yet.'}
        </p>
        <dl className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Layers className="size-3.5" aria-hidden="true" />
            <dt className="sr-only">Modules</dt>
            <dd>{course.module_count} modules</dd>
          </div>
          <div className="flex items-center gap-1.5">
            <BookOpen className="size-3.5" aria-hidden="true" />
            <dt className="sr-only">Lessons</dt>
            <dd>{course.lesson_count} lessons</dd>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="size-3.5" aria-hidden="true" />
            <dt className="sr-only">Duration</dt>
            <dd>{formatDuration(course.estimated_duration_minutes)}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
