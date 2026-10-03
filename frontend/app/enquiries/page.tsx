"use client";

/**
 * Enquiries: the admissions pipeline. A row per lead, filtered by stage from
 * the counts strip, searchable by name, mobile or email. A new enquiry is
 * entered through the enquiry form, so it lands here the same way a
 * website or Meritto lead would and starts the same automation rules.
 */

import Link from "next/link";
import { useState } from "react";
import { Plus } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { Pagination } from "@/components/pagination";
import { RequireAuth } from "@/components/require-auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/layout";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { Capability, can } from "@/lib/capabilities";
import { enquiryListPath } from "@/lib/enquiries";
import { formatDateTime } from "@/lib/format";
import { ENQUIRY_STAGE_LABEL, ENQUIRY_STAGE_VARIANT, ENQUIRY_STAGES } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { Enquiry, EnquiryStage, EnquirySummary, Paginated } from "@/types/api";

/** The server's page size (`DefaultPagination.page_size`). */
const PAGE_SIZE = 25;

function StageStrip({
  summary,
  stage,
  onStage,
}: {
  summary: EnquirySummary | null;
  stage: EnquiryStage | "";
  onStage: (stage: EnquiryStage | "") => void;
}) {
  const items: { value: EnquiryStage | ""; label: string; count: number | null }[] = [
    { value: "", label: "All", count: summary?.total ?? null },
    ...ENQUIRY_STAGES.map((value) => ({
      value,
      label: ENQUIRY_STAGE_LABEL[value],
      count: summary ? summary.stages[value] : null,
    })),
  ];
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by stage">
      {items.map((item) => (
        <button
          key={item.value || "all"}
          type="button"
          aria-pressed={stage === item.value}
          onClick={() => onStage(item.value)}
          className={cn(
            "inline-flex items-center gap-2 rounded-pill border px-3 py-1 text-xs font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
            stage === item.value
              ? "border-action bg-selected text-selected-fg"
              : "border-line bg-surface text-ink-muted hover:border-line-strong hover:text-ink",
          )}
        >
          {item.label}
          {item.count !== null ? (
            <span className="tabular-nums text-ink-faint">{item.count}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

function EnquiriesWorkspace() {
  const { user } = useAuth();
  const mayCapture = can(user?.capabilities, Capability.formAssign);
  const [stage, setStage] = useState<EnquiryStage | "">("");
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const summary = useApi<EnquirySummary>("/api/v1/enquiries/summary/");
  const list = useApi<Paginated<Enquiry>>(
    enquiryListPath({ stage, owner: mine ? "me" : undefined, q: search.trim(), page }),
  );
  const rows = list.data?.results ?? [];
  // Read once per page load: "late" only needs to be right to the minute.
  const [now] = useState(() => Date.now());

  return (
    <div className="space-y-6">
      <PageHeader title="Enquiries" meta="Every lead at your centre, by stage of the admissions pipeline.">
        {mayCapture ? (
          <Button asChild>
            <Link href="/forms/fill/enquiry">
              <Plus className="size-4" aria-hidden="true" />
              New enquiry
            </Link>
          </Button>
        ) : null}
      </PageHeader>

      <StageStrip
        summary={summary.data}
        stage={stage}
        onStage={(next) => {
          setStage(next);
          setPage(1);
        }}
      />

      <div className="flex flex-wrap items-center gap-4">
        <Input
          aria-label="Search enquiries"
          placeholder="Search name, mobile or email"
          value={search}
          className="max-w-xs"
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={mine}
            onCheckedChange={(checked) => {
              setMine(checked);
              setPage(1);
            }}
          />
          Only mine
        </label>
      </div>

      {list.isLoading ? (
        <LoadingState label="Loading enquiries…" rows={6} />
      ) : list.error ? (
        <ErrorState
          title="Could not load enquiries"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title={stage || search || mine ? "No enquiries match" : "No enquiries yet"}
          description={
            stage || search || mine
              ? "Try another stage or clear the search."
              : "Enquiries appear here when the enquiry form is filled in."
          }
        />
      ) : (
        <div className="space-y-3">
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Enquiry</Th>
                  <Th>Course</Th>
                  <Th>Source</Th>
                  <Th>Stage</Th>
                  <Th>Owner</Th>
                  <Th>Next follow-up</Th>
                  <Th>Created</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const followUpLate =
                    row.next_follow_up_at !== null && new Date(row.next_follow_up_at).getTime() < now;
                  return (
                    <tr key={row.id} className="hover:bg-sunken/40">
                      <Td>
                        <Link
                          href={`/enquiries/${row.id}`}
                          className="font-medium text-ink underline-offset-2 hover:underline"
                        >
                          {row.full_name}
                        </Link>
                        <span className="block text-2xs tabular-nums text-ink-faint">{row.mobile}</span>
                      </Td>
                      <Td>{row.course || "—"}</Td>
                      <Td>{row.source || "—"}</Td>
                      <Td>
                        <Badge variant={ENQUIRY_STAGE_VARIANT[row.stage]}>
                          {ENQUIRY_STAGE_LABEL[row.stage]}
                        </Badge>
                      </Td>
                      <Td>{row.owner?.name ?? "Unassigned"}</Td>
                      <Td className={cn("whitespace-nowrap tabular-nums", followUpLate && "text-danger")}>
                        {row.next_follow_up_at ? formatDateTime(row.next_follow_up_at) : "—"}
                      </Td>
                      <Td className="whitespace-nowrap tabular-nums">{formatDateTime(row.created_at)}</Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </TableWrapper>
          {list.data && (list.data.next || list.data.previous) ? (
            <Pagination
              page={page}
              totalPages={Math.max(1, Math.ceil(list.data.count / PAGE_SIZE))}
              count={list.data.count}
              pageSize={PAGE_SIZE}
              onPageChange={setPage}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function EnquiriesPage() {
  return (
    <RequireAuth capability={Capability.enquiryViewAny}>
      <EnquiriesWorkspace />
    </RequireAuth>
  );
}
