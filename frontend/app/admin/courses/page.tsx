'use client';

/**
 * The course catalogue, as the reference product lists it: a count in the
 * heading, Show All / Active / Archived across the top, an optional grouping
 * by standard, and a row menu holding Change Fees, Edit, Archive and Delete.
 *
 * A table rather than the card grid it used to be. A hundred and forty-four
 * courses as cards is eleven screens of scrolling, and the questions actually
 * asked of this screen — what does it cost, is it still on sale, how many are
 * under this standard — are column questions.
 *
 * One page still serves administrators and trainers, and the difference is
 * which endpoint it reads: an administrator sees everything through the
 * catalogue endpoint, a trainer only their assigned courses through
 * `/courses/mine/`. The server decides both.
 */

import Link from 'next/link';
import { Fragment, useState } from 'react';
import { Archive, ArchiveRestore, IndianRupee, Pencil, Trash2 } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { ChangeFeesDialog } from '@/components/courses/change-fees-dialog';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { RowActions } from '@/components/row-actions';
import { SavedViews } from '@/components/saved-views';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useList } from '@/hooks/use-list';
import { errorMessage } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { deleteCourse } from '@/lib/course-fees';
import { STATUS_LABEL, STATUS_VARIANT } from '@/lib/course-labels';
import { listCourses, listMyCourses, setCourseStatus } from '@/lib/courses';
import { formatRupees } from '@/lib/format';
import type { CourseListRow } from '@/types/api';

/** Show All / Active / Archived, and what each asks the server for. */
const SHELVES = [
  { key: 'all', label: 'Show All', active: undefined },
  { key: 'active', label: 'Active', active: 'true' },
  { key: 'archived', label: 'Archived', active: 'false' },
] as const;

function CourseAdminList() {
  const { can } = useAuth();
  const isAdmin = can(Capability.courseViewAny);
  const list = useList<CourseListRow>(
    isAdmin ? listCourses : listMyCourses,
    { page_size: 20 },
    { urlKeys: ['status', 'active'] },
  );
  const [byStandard, setByStandard] = useState(false);
  const [feesFor, setFeesFor] = useState<CourseListRow | null>(null);
  const [deleting, setDeleting] = useState<CourseListRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const rows = list.data?.results ?? [];
  const shelf = SHELVES.find((item) => (item.active ?? '') === String(list.query.active ?? ''));

  async function archive(course: CourseListRow, archived: boolean) {
    setBusy(true);
    setFailure(null);
    try {
      await setCourseStatus(course.id, archived ? 'archived' : 'draft');
      setNotice(
        archived
          ? `${course.title} is archived. It keeps everything and leaves the catalogue.`
          : `${course.title} is back as a draft.`,
      );
      list.reload();
    } catch (cause) {
      setFailure(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function destroy(course: CourseListRow) {
    setBusy(true);
    setFailure(null);
    try {
      await deleteCourse(course.id);
      setDeleting(null);
      setNotice(`${course.title} is deleted.`);
      list.reload();
    } catch (cause) {
      // The server refuses a course with batches or enrolments and says to
      // archive it instead. That sentence is the useful one, so it is shown
      // where the person is looking rather than swallowed.
      setFailure(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  /** Rows under their standard, in the order the standards first appear. */
  function grouped(): [string, CourseListRow[]][] {
    const groups = new Map<string, CourseListRow[]>();
    for (const row of rows) {
      const key = row.category_name || 'No standard';
      const bucket = groups.get(key);
      if (bucket) bucket.push(row);
      else groups.set(key, [row]);
    }
    return [...groups.entries()];
  }

  function row(course: CourseListRow) {
    return (
      <tr key={course.id} className="hover:bg-sunken/40">
        <Td>
          <Link href={`/admin/courses/${course.id}`} className="font-medium hover:text-action">
            {course.title}
          </Link>
          <p className="font-mono text-xs text-ink-muted">{course.code}</p>
        </Td>
        {byStandard ? null : <Td>{course.category_name}</Td>}
        <Td className="whitespace-nowrap tabular-nums">{formatRupees(course.default_fee)}</Td>
        <Td className="tabular-nums">
          {course.module_count} / {course.lesson_count}
        </Td>
        <Td>
          <Badge variant={STATUS_VARIANT[course.status]}>{STATUS_LABEL[course.status]}</Badge>
        </Td>
        <Td>
          <RowActions
            subject={course.title}
            actions={[
              {
                label: 'Change Fees',
                icon: IndianRupee,
                capability: Capability.courseUpdateAny,
                onSelect: () => setFeesFor(course),
              },
              {
                label: 'Edit',
                icon: Pencil,
                capability: Capability.courseUpdateAny,
                href: `/admin/courses/${course.id}`,
              },
              course.status === 'archived'
                ? {
                    label: 'Unarchive',
                    icon: ArchiveRestore,
                    capability: Capability.coursePublishAny,
                    onSelect: () => void archive(course, false),
                  }
                : {
                    label: 'Archive',
                    icon: Archive,
                    capability: Capability.coursePublishAny,
                    onSelect: () => void archive(course, true),
                  },
              {
                label: 'Delete',
                icon: Trash2,
                destructive: true,
                capability: Capability.courseDelete,
                onSelect: () => {
                  setFailure(null);
                  setDeleting(course);
                },
              },
            ]}
          />
        </Td>
      </tr>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1
            className="text-2xl font-semibold tracking-tight"
            // The count is a second element so it can be set in a lighter
            // weight, and the accessible name computation joins text nodes
            // without a space — "Courses2". The label spells it properly.
            aria-label={
              list.data
                ? `${isAdmin ? 'Courses' : 'My courses'} (${list.data.count})`
                : undefined
            }
          >
            {isAdmin ? 'Courses' : 'My courses'}
            {list.data ? (
              <span className="ml-2 text-xl font-normal text-ink-muted">({list.data.count})</span>
            ) : null}
          </h1>
          <p className="text-sm text-ink-muted">
            {isAdmin
              ? 'Every course on the platform, including drafts and archived ones.'
              : 'Courses you have been assigned to author.'}
          </p>
        </div>
        <div className="flex gap-2">
          {can(Capability.categoryManage) ? (
            <Button asChild variant="outline">
              <Link href="/admin/categories">Standards</Link>
            </Button>
          ) : null}
          {can(Capability.courseCreate) ? (
            <Button asChild>
              <Link href="/admin/courses/new">New course</Link>
            </Button>
          ) : null}
        </div>
      </div>

      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {/* While the delete dialog is open it carries the failure itself —
          showing it in both places says the same thing twice, over the thing
          the person is reading. */}
      {failure && !deleting ? <Alert variant="error">{failure}</Alert> : null}

      {isAdmin ? (
        <Tabs
          value={shelf?.key ?? 'all'}
          onValueChange={(key) => {
            const picked = SHELVES.find((item) => item.key === key);
            list.setQuery({ active: picked?.active ?? '' });
          }}
        >
          <TabsList>
            {SHELVES.map((item) => (
              <TabsTrigger key={item.key} value={item.key}>
                {item.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      ) : null}

      <SavedViews
        screen="admin-courses"
        keys={['search', 'ordering', 'status', 'active']}
        query={list.query}
        onApply={list.setQuery}
      />
      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Course title or code"
      >
        <div className="flex items-end gap-2 pb-0.5">
          <Switch
            id="by-standard"
            aria-label="By standard"
            checked={byStandard}
            onCheckedChange={setByStandard}
          />
          <label htmlFor="by-standard" className="text-sm">
            By standard
          </label>
        </div>
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
      ) : rows.length === 0 ? (
        <EmptyState
          title={isAdmin ? 'No courses here' : 'No courses assigned to you'}
          description={
            isAdmin
              ? 'Nothing matches this shelf and search.'
              : 'An administrator assigns courses for you to author.'
          }
        />
      ) : (
        <>
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Course</Th>
                  {byStandard ? null : <Th>Standard</Th>}
                  <Th>Course Fees</Th>
                  <Th>Subjects / Lessons</Th>
                  <Th>Status</Th>
                  <Th>
                    <span className="sr-only">Action</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {byStandard
                  ? grouped().map(([standard, courses]) => (
                      <Fragment key={standard}>
                        <tr className="bg-sunken/60">
                          <Td colSpan={5} className="text-sm font-medium">
                            {standard}
                            <span className="ml-2 font-normal text-ink-muted">
                              ({courses.length})
                            </span>
                          </Td>
                        </tr>
                        {courses.map((course) => row(course))}
                      </Fragment>
                    ))
                  : rows.map((course) => row(course))}
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

      {feesFor ? (
        <ChangeFeesDialog
          course={feesFor}
          open
          onClose={() => setFeesFor(null)}
          onSaved={(message) => {
            setFeesFor(null);
            setNotice(message);
            list.reload();
          }}
        />
      ) : null}

      <Dialog
        open={Boolean(deleting)}
        onOpenChange={(next) => (next ? undefined : setDeleting(null))}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {deleting?.title}?</DialogTitle>
            <DialogDescription>
              This destroys the course and its content. It cannot be undone, and it is refused if
              anybody has been taught under it — archiving is what that case wants, and it keeps
              the record.
            </DialogDescription>
          </DialogHeader>
          {failure ? <Alert variant="error">{failure}</Alert> : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={busy}
              onClick={() => deleting && void destroy(deleting)}
            >
              {busy ? 'Deleting…' : 'Delete course'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function AdminCoursesPage() {
  return (
    <RequireAuth capability={Capability.courseViewAny} roles={['trainer']}>
      <CourseAdminList />
    </RequireAuth>
  );
}
