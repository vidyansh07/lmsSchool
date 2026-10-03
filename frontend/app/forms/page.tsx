"use client";

/**
 * Forms: what has been sent to me to fill, what I sent, and — for the
 * people who read submissions — every form at my centre. Anyone who may
 * send forms also gets "Fill in a form", for entering an enquiry or any
 * other form directly.
 */

import Link from "next/link";
import { useState } from "react";
import { ClipboardList } from "lucide-react";

import { FormAssignmentsTable } from "@/components/forms/form-assignments-table";
import { Pagination } from "@/components/pagination";
import { RequireAuth } from "@/components/require-auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { useAuth } from "@/components/auth-provider";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/layout";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/hooks/use-api";
import { Capability, can } from "@/lib/capabilities";
import { FORM_ENTITY_LABEL } from "@/lib/labels";
import type { FormAssignmentBox } from "@/lib/forms";
import type { FillableForm, FormAssignment, Paginated } from "@/types/api";

/** The server's page size (`DefaultPagination.page_size`). */
const PAGE_SIZE = 25;

const BOX_EMPTY: Record<FormAssignmentBox, { title: string; description: string }> = {
  inbox: {
    title: "Nothing to fill in",
    description: "Forms sent to you, by a colleague or by an automation rule, appear here.",
  },
  sent: {
    title: "You have not sent any forms",
    description: "Open a form and choose Send to someone, or let an automation rule send it.",
  },
  all: {
    title: "No forms at your centre yet",
    description: "Every form sent or filled in at your centre appears here.",
  },
};

function AssignmentList({ box }: { box: FormAssignmentBox }) {
  const [page, setPage] = useState(1);
  const { data, error, isLoading, reload } = useApi<Paginated<FormAssignment>>(
    `/api/v1/forms/assignments/?box=${box}&page=${page}`,
  );

  if (isLoading) return <LoadingState label="Loading forms…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load forms"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={reload}
      />
    );
  }
  const rows = data?.results ?? [];
  if (rows.length === 0) {
    return <EmptyState title={BOX_EMPTY[box].title} description={BOX_EMPTY[box].description} />;
  }
  return (
    <div className="space-y-3">
      <FormAssignmentsTable rows={rows} showAssignee={box !== "inbox"} />
      {data && (data.next || data.previous) ? (
        <Pagination
          page={page}
          totalPages={Math.max(1, Math.ceil(data.count / PAGE_SIZE))}
          count={data.count}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
        />
      ) : null}
    </div>
  );
}

function FillableForms() {
  const { data, error, isLoading, reload } = useApi<FillableForm[]>("/api/v1/forms/fillable/");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Fill in a form</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingState label="Loading forms…" rows={2} />
        ) : error ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No published forms yet. An administrator builds them under Admin → Forms.
          </p>
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.map((form) => (
              <li key={form.slug}>
                <Link
                  href={`/forms/fill/${form.slug}`}
                  className="flex items-center gap-3 rounded-control border border-line px-3 py-2.5 text-sm hover:border-line-strong hover:bg-sunken/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
                >
                  <ClipboardList className="size-4 shrink-0 text-ink-faint" aria-hidden="true" />
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-ink">{form.name}</span>
                    <span className="block text-2xs text-ink-faint">
                      {FORM_ENTITY_LABEL[form.entity] ?? form.entity}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function FormsWorkspace() {
  const { user } = useAuth();
  const maySend = can(user?.capabilities, Capability.formAssign);
  const mayReadAll = can(user?.capabilities, Capability.formView);
  const [box, setBox] = useState<FormAssignmentBox>("inbox");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Forms"
        meta="Forms sent to you to fill, and the ones you sent."
      />

      {maySend ? <FillableForms /> : null}

      {maySend || mayReadAll ? (
        <Tabs value={box} onValueChange={(value) => setBox(value as FormAssignmentBox)}>
          <TabsList>
            <TabsTrigger value="inbox">To fill</TabsTrigger>
            {maySend ? <TabsTrigger value="sent">Sent</TabsTrigger> : null}
            {mayReadAll ? <TabsTrigger value="all">All at my centre</TabsTrigger> : null}
          </TabsList>
        </Tabs>
      ) : null}

      <AssignmentList key={box} box={box} />
    </div>
  );
}

export default function FormsPage() {
  return (
    <RequireAuth>
      <FormsWorkspace />
    </RequireAuth>
  );
}
