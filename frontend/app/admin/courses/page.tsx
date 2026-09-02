'use client';

import Link from 'next/link';
import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { CourseCard } from '@/components/course-card';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/input';
import { useList } from '@/hooks/use-list';
import { Capability } from '@/lib/capabilities';
import { listCourses, listMyCourses } from '@/lib/courses';
import { STATUS_LABEL } from '@/lib/course-labels';
import type { CourseListRow, PublishStatus } from '@/types/api';
import { CreateCourseDialog } from './create-course-dialog';

const STATUS_OPTIONS: PublishStatus[] = ['draft', 'in_review', 'published', 'archived'];

/**
 * One page serves administrators and trainers.
 *
 * The difference is which endpoint it reads: an administrator sees everything
 * through the catalogue endpoint, a trainer sees only their assigned courses
 * through `/courses/mine/`. The server decides both — the page just picks the
 * right question to ask.
 */
function CourseAdminList() {
  const { can } = useAuth();
  const isAdmin = can(Capability.courseViewAny);
  const list = useList<CourseListRow>(isAdmin ? listCourses : listMyCourses, { page_size: 12 });
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            {isAdmin ? 'Courses' : 'My courses'}
          </h1>
          <p className="text-sm text-muted-foreground">
            {isAdmin
              ? 'Every course on the platform, including drafts.'
              : 'Courses you have been assigned to author.'}
          </p>
        </div>
        <div className="flex gap-2">
          {can(Capability.categoryManage) ? (
            <Button asChild variant="outline">
              <Link href="/admin/categories">Categories</Link>
            </Button>
          ) : null}
          {can(Capability.courseCreate) ? (
            <Button onClick={() => setShowCreate(true)}>New course</Button>
          ) : null}
        </div>
      </div>

      {showCreate ? (
        <CreateCourseDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            list.reload();
          }}
        />
      ) : null}

      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Course title or code"
      >
        {isAdmin ? (
          <div>
            <label htmlFor="filter-status" className="mb-1.5 block text-sm font-medium">
              Status
            </label>
            <Select
              id="filter-status"
              value={String(list.query.status ?? '')}
              onChange={(event) => list.setQuery({ status: event.target.value })}
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((value) => (
                <option key={value} value={value}>
                  {STATUS_LABEL[value]}
                </option>
              ))}
            </Select>
          </div>
        ) : null}
      </ListToolbar>

      {list.isLoading ? (
        <LoadingState label="Loading courses…" rows={6} />
      ) : list.error ? (
        <ErrorState
          title="Could not load courses"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : list.data && list.data.count === 0 ? (
        <EmptyState
          title={isAdmin ? 'No courses yet' : 'No courses assigned to you'}
          description={
            isAdmin
              ? 'Create the first course to get started.'
              : 'An administrator assigns courses for you to author.'
          }
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {list.data?.results.map((course) => (
              <CourseCard
                key={course.id}
                course={course}
                href={`/admin/courses/${course.id}`}
                showStatus
              />
            ))}
          </div>
          {list.data ? (
            <Pagination
              page={list.data.page}
              totalPages={list.data.total_pages}
              count={list.data.count}
              pageSize={list.data.page_size}
              onPageChange={list.setPage}
            />
          ) : null}
        </>
      )}
    </div>
  );
}

export default function AdminCoursesPage() {
  return (
    <RequireAuth>
      <CourseAdminList />
    </RequireAuth>
  );
}
