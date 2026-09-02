'use client';

import { useEffect, useState } from 'react';

import { CourseCard } from '@/components/course-card';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Select } from '@/components/ui/input';
import { useList } from '@/hooks/use-list';
import { listCategories, listCourses } from '@/lib/courses';
import { DIFFICULTY_OPTIONS } from '@/lib/course-labels';
import type { Category, CourseListRow } from '@/types/api';

function Catalog() {
  const list = useList<CourseListRow>(listCourses, { page_size: 9 });
  const [categories, setCategories] = useState<Category[]>([]);

  useEffect(() => {
    let cancelled = false;
    listCategories({ page_size: 100 })
      .then((page) => {
        if (!cancelled) setCategories(page.results);
      })
      .catch(() => {
        // A failed filter list is not worth blocking the catalogue for.
        if (!cancelled) setCategories([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Course catalogue</h1>
        <p className="text-sm text-muted-foreground">
          Browse the courses available to you. Unpublished courses are not listed.
        </p>
      </div>

      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Course title, code or description"
      >
        <div>
          <label htmlFor="filter-category" className="mb-1.5 block text-sm font-medium">
            Category
          </label>
          <Select
            id="filter-category"
            value={String(list.query.category ?? '')}
            onChange={(event) => list.setQuery({ category: event.target.value })}
          >
            <option value="">All categories</option>
            {categories.map((category) => (
              <option key={category.id} value={category.slug}>
                {category.name}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="filter-difficulty" className="mb-1.5 block text-sm font-medium">
            Difficulty
          </label>
          <Select
            id="filter-difficulty"
            value={String(list.query.difficulty ?? '')}
            onChange={(event) => list.setQuery({ difficulty: event.target.value })}
          >
            <option value="">Any level</option>
            {DIFFICULTY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
      </ListToolbar>

      {list.isLoading ? (
        <LoadingState label="Loading courses…" rows={6} />
      ) : list.error ? (
        <ErrorState
          title="Could not load the catalogue"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : list.data && list.data.count === 0 ? (
        <EmptyState
          title="No courses match these filters"
          description="Try a different search term, or clear the filters."
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {list.data?.results.map((course) => (
              <CourseCard key={course.id} course={course} href={`/courses/${course.slug}`} />
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

export default function CoursesPage() {
  return (
    <RequireAuth>
      <Catalog />
    </RequireAuth>
  );
}
