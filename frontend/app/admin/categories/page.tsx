'use client';

import { useState } from 'react';

import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { useList } from '@/hooks/use-list';
import { ApiError, fieldErrors } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { createCategory, listCategories, updateCategory } from '@/lib/courses';
import type { Category } from '@/types/api';

function CategoryAdmin() {
  const list = useList<Category>(listCategories, { page_size: 25 });
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    setErrors({});
    setMessage('');
    try {
      await createCategory({ name, slug: slug || undefined });
      setName('');
      setSlug('');
      list.reload();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    }
  }

  async function onToggleActive(category: Category) {
    try {
      await updateCategory(category.id, { is_active: !category.is_active });
      list.reload();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'Could not update the category.');
    }
  }

  return (
    <div className="animate-rise-in space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Course categories</h1>
        <p className="text-sm text-muted-foreground">
          Categories group the catalogue. Retiring one hides it from filters but keeps its courses.
        </p>
      </div>

      <form
        onSubmit={onCreate}
        className="flex flex-wrap items-end gap-3 rounded-[var(--radius-card)] border border-border p-4"
      >
        <Field label="Name" htmlFor="category-name" error={errors.name} className="min-w-[14rem] flex-1">
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field
          label="Slug"
          htmlFor="category-slug"
          error={errors.slug}
          hint="Optional — generated from the name."
          className="min-w-[14rem] flex-1"
        >
          <Input value={slug} onChange={(event) => setSlug(event.target.value)} />
        </Field>
        <Button type="submit">Add category</Button>
      </form>

      {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
      {message ? <Alert variant="error">{message}</Alert> : null}

      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Category name or slug"
      />

      {list.isLoading ? (
        <LoadingState label="Loading categories…" rows={4} />
      ) : list.error ? (
        <ErrorState
          title="Could not load categories"
          message={list.error.message}
          onRetry={list.reload}
        />
      ) : list.data && list.data.count === 0 ? (
        <EmptyState title="No categories yet" description="Add the first one above." />
      ) : (
        <>
          <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
            <Table>
              <thead>
                <tr>
                  <Th className="sticky top-0 z-10 bg-muted">Name</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Slug</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Published courses</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Status</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Actions</Th>
                </tr>
              </thead>
              <tbody className="stagger">
                {list.data?.results.map((category) => (
                  <tr key={category.id} className="animate-fade-in transition-colors hover:bg-muted/40">
                    <Td className="font-medium">{category.name}</Td>
                    <Td className="font-mono text-xs">{category.slug}</Td>
                    <Td>{category.course_count}</Td>
                    <Td>
                      <Badge variant={category.is_active ? 'success' : 'neutral'}>
                        {category.is_active ? 'Active' : 'Retired'}
                      </Badge>
                    </Td>
                    <Td>
                      <Button size="sm" variant="outline" onClick={() => void onToggleActive(category)}>
                        {category.is_active ? 'Retire' : 'Restore'}
                      </Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>

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

export default function AdminCategoriesPage() {
  return (
    <RequireAuth capability={Capability.categoryManage}>
      <CategoryAdmin />
    </RequireAuth>
  );
}
