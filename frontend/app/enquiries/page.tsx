"use client";

/**
 * Enquiries: the admissions pipeline. A row per lead, kept in two piles —
 * online (website, Google, social media, WhatsApp) and offline (walk-ins,
 * phone calls, referrals, seminars) — with the totals of each at the top,
 * filtered by stage from the counts strip, by source, by follow-up state and
 * by date, searchable by name, mobile or email. Stage and source are changed
 * from the row itself, one select each, so a counsellor working the phone
 * never has to open a lead just to move it on.
 *
 * A new enquiry is entered through the enquiry form, so it lands here the
 * same way a website or Meritto lead would and starts the same automation
 * rules.
 */

import Link from "next/link";
import { useState } from "react";
import { Plus } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { BulkActionsBar, type BulkAction } from "@/components/bulk-actions";
import { BulkResultDialog } from "@/components/bulk-result-dialog";
import { Pagination } from "@/components/pagination";
import { RequireAuth } from "@/components/require-auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/layout";
import { StatStrip } from "@/components/ui/stat-strip";
import { StaffSelect } from "@/components/staff-select";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { useBulkSelection } from "@/hooks/use-bulk-selection";
import { errorMessage, fieldErrors } from "@/lib/api";
import { bulkAssignEnquiryOwner, bulkTarget, type BulkResult } from "@/lib/bulk";
import { Capability, can } from "@/lib/capabilities";
import { enquiryListPath, updateEnquiry, type EnquiryFollowUpFilter } from "@/lib/enquiries";
import { formatCount, formatDateTime } from "@/lib/format";
import {
  ENQUIRY_STAGE_LABEL,
  ENQUIRY_STAGE_VARIANT,
  ENQUIRY_STAGES,
  LEAD_CHANNEL_LABEL,
} from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { Enquiry, EnquiryStage, EnquirySummary, LeadChannel, Paginated } from "@/types/api";

/** The server's page size (`DefaultPagination.page_size`). */
const PAGE_SIZE = 25;

const CHANNEL_TABS: { value: LeadChannel | ""; label: string }[] = [
  { value: "", label: "All leads" },
  { value: "online", label: "Online" },
  { value: "offline", label: "Offline" },
];

const FOLLOW_UP_OPTIONS: { value: EnquiryFollowUpFilter; label: string }[] = [
  { value: "", label: "Any follow-up" },
  { value: "overdue", label: "Follow-up overdue" },
  { value: "today", label: "Follow-up today" },
  { value: "none", label: "No follow-up planned" },
];

function pillClass(active: boolean): string {
  return cn(
    "inline-flex items-center gap-2 rounded-pill border px-3 py-1 text-xs font-medium transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
    active
      ? "border-action bg-selected text-selected-fg"
      : "border-line bg-surface text-ink-muted hover:border-line-strong hover:text-ink",
  );
}

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
    { value: "", label: "All stages", count: summary?.total ?? null },
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
          className={pillClass(stage === item.value)}
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

function ChannelTabs({
  summary,
  channel,
  onChannel,
}: {
  summary: EnquirySummary | null;
  channel: LeadChannel | "";
  onChannel: (channel: LeadChannel | "") => void;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Online or offline">
      {CHANNEL_TABS.map((tab) => {
        const count =
          summary === null ? null : tab.value === "" ? summary.total : summary.channels[tab.value];
        return (
          <button
            key={tab.value || "all"}
            type="button"
            aria-pressed={channel === tab.value}
            onClick={() => onChannel(tab.value)}
            className={pillClass(channel === tab.value)}
          >
            {tab.label}
            {count !== null ? <span className="tabular-nums text-ink-faint">{count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

/** The list's filters as the bulk endpoint reads them (`EnquiryFilterSet`). */
const ENQUIRY_FILTER_KEYS = [
  "stage",
  "channel",
  "source",
  "follow_up",
  "created_after",
  "created_before",
  "owner",
  "q",
] as const;

function AssignOwnerDialog({
  open,
  count,
  onClose,
  onAssign,
}: {
  open: boolean;
  count: number;
  onClose: () => void;
  onAssign: (ownerId: string | null) => Promise<Record<string, string> | null>;
}) {
  const [owner, setOwner] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!owner) {
      setErrors({ owner_id: "Choose who takes them, or nobody." });
      return;
    }
    setBusy(true);
    const refused = await onAssign(owner === "none" ? null : owner);
    setBusy(false);
    if (refused) setErrors(refused);
    else {
      setOwner("");
      setErrors({});
    }
  }

  const formError = errors.filters ?? errors.ids ?? errors.detail;

  return (
    <Dialog open={open} onOpenChange={(next) => (next || busy ? null : onClose())}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Assign {formatCount(count, "enquiry", "enquiries")}</DialogTitle>
          <DialogDescription>
            They appear in the new owner&apos;s list and follow-ups. Enquiries you cannot change, or
            at another centre than the owner, are skipped and listed.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
          {formError ? <Alert variant="error">{formError}</Alert> : null}
          <Field label="Owner" htmlFor="bulk-owner" error={errors.owner_id} required>
            <StaffSelect id="bulk-owner" value={owner} onChange={setOwner} allowNone autoFocus />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Assigning…" : "Assign"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EnquiriesWorkspace() {
  const { user } = useAuth();
  const mayCapture = can(user?.capabilities, Capability.formAssign);
  const [stage, setStage] = useState<EnquiryStage | "">("");
  const [channel, setChannel] = useState<LeadChannel | "">("");
  const [source, setSource] = useState("");
  const [followUp, setFollowUp] = useState<EnquiryFollowUpFilter>("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [savingId, setSavingId] = useState("");
  const [saveError, setSaveError] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [result, setResult] = useState<BulkResult | null>(null);
  const mayManage = can(user?.capabilities, Capability.enquiryManage);

  const summary = useApi<EnquirySummary>("/api/v1/enquiries/summary/");
  const list = useApi<Paginated<Enquiry>>(
    enquiryListPath({
      stage,
      channel,
      source,
      follow_up: followUp,
      created_after: createdAfter,
      created_before: createdBefore,
      owner: mine ? "me" : undefined,
      q: search.trim(),
      page,
    }),
  );
  const rows = list.data?.results ?? [];
  const query: Record<string, string> = {
    stage,
    channel,
    source,
    follow_up: followUp,
    created_after: createdAfter,
    created_before: createdBefore,
    owner: mine ? "me" : "",
    q: search.trim(),
  };
  // Ticked rows survive paging but never a change of filter.
  const selection = useBulkSelection<string>(JSON.stringify(query));
  const pageIds = rows.map((row) => row.id);
  const pageState = selection.pageSelectionState(pageIds);
  const selectedCount = selection.selectAllMatching
    ? (list.data?.count ?? 0)
    : selection.selectedCount;

  async function assignOwner(ownerId: string | null): Promise<Record<string, string> | null> {
    try {
      const done = await bulkAssignEnquiryOwner({
        // `q` is this list's search; the bulk endpoint reads it as a filter.
        ...bulkTarget(selection, query, ENQUIRY_FILTER_KEYS),
        owner_id: ownerId,
      });
      setAssigning(false);
      setResult(done);
      selection.clear();
      list.reload();
      return null;
    } catch (cause) {
      return fieldErrors(cause);
    }
  }

  const bulkActions: BulkAction[] = mayManage
    ? [{ id: "assign", label: "Assign owner", onClick: () => setAssigning(true) }]
    : [];
  // Read once per page load: "late" only needs to be right to the minute.
  const [now] = useState(() => Date.now());
  const sources = summary.data?.sources ?? [];
  const sourceLabel = (value: string) =>
    sources.find((option) => option.value === value)?.label ?? value;
  const filtered =
    Boolean(stage || channel || source || followUp || createdAfter || createdBefore || search || mine);

  function resetPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  async function changeRow(row: Enquiry, changes: { stage?: EnquiryStage; source?: string }) {
    setSavingId(row.id);
    setSaveError("");
    try {
      await updateEnquiry(row.id, changes);
      list.reload();
      summary.reload();
    } catch (cause) {
      setSaveError(errorMessage(cause, "Could not save that change."));
    } finally {
      setSavingId("");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Enquiries"
        meta="Every lead at your centre, online and offline, by stage of the admissions pipeline."
      >
        {mayCapture ? (
          <Button asChild>
            <Link href="/forms/fill/enquiry">
              <Plus className="size-4" aria-hidden="true" />
              New enquiry
            </Link>
          </Button>
        ) : null}
      </PageHeader>

      <StatStrip
        items={[
          { label: "Online leads", value: summary.data?.channels.online ?? null },
          { label: "Offline leads", value: summary.data?.channels.offline ?? null },
          { label: "Total leads", value: summary.data?.total ?? null },
        ]}
      />

      <ChannelTabs summary={summary.data} channel={channel} onChannel={resetPage(setChannel)} />
      <StageStrip summary={summary.data} stage={stage} onStage={resetPage(setStage)} />

      <div className="flex flex-wrap items-end gap-3">
        <Input
          aria-label="Search enquiries"
          placeholder="Search name, mobile or email"
          value={search}
          className="max-w-xs"
          onChange={(event) => resetPage(setSearch)(event.target.value)}
        />
        <Select
          aria-label="Filter by source"
          value={source}
          className="max-w-[12rem]"
          onChange={(event) => resetPage(setSource)(event.target.value)}
        >
          <option value="">Any source</option>
          {sources.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Filter by follow-up"
          value={followUp}
          className="max-w-[12rem]"
          onChange={(event) => resetPage(setFollowUp)(event.target.value as EnquiryFollowUpFilter)}
        >
          {FOLLOW_UP_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <label className="flex items-center gap-1 text-sm text-ink-muted">
          From
          <Input
            type="date"
            aria-label="Created from"
            value={createdAfter}
            onChange={(event) => resetPage(setCreatedAfter)(event.target.value)}
          />
        </label>
        <label className="flex items-center gap-1 text-sm text-ink-muted">
          To
          <Input
            type="date"
            aria-label="Created up to"
            value={createdBefore}
            onChange={(event) => resetPage(setCreatedBefore)(event.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={mine} onCheckedChange={resetPage(setMine)} />
          Only mine
        </label>
      </div>

      {saveError ? <Alert variant="error">{saveError}</Alert> : null}

      <BulkActionsBar
        selectedCount={selection.selectedCount}
        totalMatchingCount={list.data?.count}
        selectAllMatching={selection.selectAllMatching}
        onSelectAllMatching={selection.selectAllMatchingFilter}
        onClear={selection.clear}
        actions={bulkActions}
        itemNoun="enquiry"
        itemPlural="enquiries"
      />
      <AssignOwnerDialog
        open={assigning}
        count={selectedCount}
        onClose={() => setAssigning(false)}
        onAssign={assignOwner}
      />
      <BulkResultDialog
        result={result}
        title="Owner assigned"
        doneLabel="assigned"
        itemNoun="enquiry"
        itemPlural="enquiries"
        onClose={() => setResult(null)}
      />

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
          title={filtered ? "No enquiries match" : "No enquiries yet"}
          description={
            filtered
              ? "Try another stage, channel or source, or clear the search."
              : "Enquiries appear here when the enquiry form is filled in."
          }
        />
      ) : (
        <div className="space-y-3">
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th className="w-10">
                    <input
                      type="checkbox"
                      aria-label="Select every enquiry on this page"
                      checked={pageState === "all"}
                      ref={(node) => {
                        if (node) node.indeterminate = pageState === "some";
                      }}
                      onChange={() => selection.toggleAll(pageIds)}
                      className="size-4 rounded border-line accent-action"
                    />
                  </Th>
                  <Th>Enquiry</Th>
                  <Th>Course</Th>
                  <Th>Source</Th>
                  <Th>Online / offline</Th>
                  <Th>Stage</Th>
                  <Th>Owner</Th>
                  <Th>Next follow-up</Th>
                  <Th>Created</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const followUpLate =
                    row.next_follow_up_at !== null && new Date(row.next_follow_up_at).getTime() < now;
                  const busy = savingId === row.id;
                  return (
                    <tr
                      key={row.id}
                      className={cn("hover:bg-sunken/40", selection.isSelected(row.id) && "bg-selected")}
                      data-testid={`enquiry-${row.id}`}
                    >
                      <Td>
                        <input
                          type="checkbox"
                          aria-label={`Select ${row.full_name}`}
                          checked={selection.isSelected(row.id)}
                          readOnly
                          onClick={(event) =>
                            selection.toggle(row.id, index, pageIds, event.shiftKey)
                          }
                          className="size-4 rounded border-line accent-action"
                        />
                      </Td>
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
                      <Td>
                        {row.can_manage ? (
                          <Select
                            aria-label={`Source of ${row.full_name}`}
                            value={row.source}
                            disabled={busy}
                            onChange={(event) => void changeRow(row, { source: event.target.value })}
                          >
                            {row.source && !sources.some((option) => option.value === row.source) ? (
                              <option value={row.source}>{row.source}</option>
                            ) : null}
                            {!row.source ? <option value="">Not known</option> : null}
                            {sources.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </Select>
                        ) : (
                          sourceLabel(row.source) || "—"
                        )}
                      </Td>
                      <Td>
                        <Badge variant={row.channel === "online" ? "info" : "neutral"}>
                          {LEAD_CHANNEL_LABEL[row.channel]}
                        </Badge>
                      </Td>
                      <Td>
                        {row.can_manage ? (
                          <Select
                            aria-label={`Stage of ${row.full_name}`}
                            value={row.stage}
                            disabled={busy}
                            onChange={(event) =>
                              void changeRow(row, { stage: event.target.value as EnquiryStage })
                            }
                          >
                            {ENQUIRY_STAGES.map((value) => (
                              <option key={value} value={value}>
                                {ENQUIRY_STAGE_LABEL[value]}
                              </option>
                            ))}
                          </Select>
                        ) : (
                          <Badge variant={ENQUIRY_STAGE_VARIANT[row.stage]}>
                            {ENQUIRY_STAGE_LABEL[row.stage]}
                          </Badge>
                        )}
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
