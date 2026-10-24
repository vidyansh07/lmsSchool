"use client";

/**
 * Automation rules: the list (`docs/erp/AUTOMATION_CATALOG.md`). Creating
 * one only asks for a name and a trigger — the trigger locks which
 * condition paths the builder offers next, so it has to be picked before
 * there is anything else useful to edit; conditions and actions are added
 * on the detail screen, matching `app/admin/forms/page.tsx`'s "New form"
 * dialog handing off to the detail route for everything else.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { History, Pencil, Plus } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { ListToolbar } from "@/components/list-toolbar";
import { RowActions } from "@/components/row-actions";
import { Pagination } from "@/components/pagination";
import { RequireAuth } from "@/components/require-auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { fieldErrors } from "@/lib/api";
import { createAutomationRule } from "@/lib/automation";
import { Capability, can } from "@/lib/capabilities";
import {
  AUTOMATION_RULE_STATUS_LABEL,
  AUTOMATION_RULE_STATUS_VARIANT,
  AUTOMATION_RECORD_LABEL,
  AUTOMATION_RECORD_TRIGGERS,
  AUTOMATION_TRIGGER_LABEL,
  AUTOMATION_TRIGGER_OPTIONS,
  automationRecordOf,
  type AutomationRecord,
} from "@/lib/labels";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AutomationRule, AutomationTrigger, Paginated } from "@/types/api";

function NewRuleDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState<AutomationTrigger>(AUTOMATION_TRIGGER_OPTIONS[0]!.value);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  function reset() {
    setName("");
    setTrigger(AUTOMATION_TRIGGER_OPTIONS[0]!.value);
    setErrors({});
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      const created = await createAutomationRule({ name: name.trim(), trigger });
      reset();
      onCreated(created.id);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent>
        <form className="space-y-4" onSubmit={(event) => void submit(event)} noValidate>
          <DialogHeader>
            <DialogTitle>New automation rule</DialogTitle>
            <DialogDescription>
              Starts as a draft with no conditions or actions. The trigger locks which
              condition paths you can pick on the next screen, so choose it now.
            </DialogDescription>
          </DialogHeader>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
          <Field label="Name" htmlFor="rule-name" error={errors.name} required>
            <Input
              id="rule-name"
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field label="Trigger" htmlFor="rule-trigger-new" error={errors.trigger} required>
            <Select
              id="rule-trigger-new"
              value={trigger}
              onChange={(event) => setTrigger(event.target.value as AutomationTrigger)}
            >
              {(Object.keys(AUTOMATION_RECORD_TRIGGERS) as AutomationRecord[]).map((record) => (
                <optgroup key={record} label={AUTOMATION_RECORD_LABEL[record]}>
                  {AUTOMATION_RECORD_TRIGGERS[record].map((value) => (
                    <option key={value} value={value}>
                      {AUTOMATION_TRIGGER_LABEL[value]}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Field>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving || !name.trim()}>
              {saving ? "Creating…" : "Create rule"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The status cards above the list, and what each one filters to.
 *
 *  The reference product shows five — active, draft, pause, completed,
 *  stopped. Only three exist here, deliberately: a rule in this system has
 *  no end of life to reach. It reacts to its trigger until somebody pauses
 *  it. Two more cards reading zero for ever would be furniture. */
const SHELVES = [
  { key: 'active', label: 'Active', tone: 'success' as const },
  { key: 'draft', label: 'Draft', tone: 'neutral' as const },
  { key: 'paused', label: 'Paused', tone: 'warning' as const },
];

interface RuleSummary {
  total: number;
  active: number;
  draft: number;
  paused: number;
}

function AutomationRulesList() {
  const router = useRouter();
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.automationManage);
  const [page, setPage] = useState(1);
  const [shelf, setShelf] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const { data, error, isLoading, reload } = useApi<Paginated<AutomationRule>>(
    `/api/v1/automation-rules/?page=${page}` +
      (shelf ? `&status=${shelf}` : '') +
      (search.trim() ? `&search=${encodeURIComponent(search.trim())}` : ''),
  );
  const summary = useApi<RuleSummary>('/api/v1/automation-rules/summary/');
  const [creating, setCreating] = useState(false);

  const rows = data?.results ?? [];
  const counts = summary.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold tracking-tight">
            Manage Automations
            {counts ? (
              <Badge variant="neutral">Total Automation — {counts.total}</Badge>
            ) : null}
          </h1>
          <p className="max-w-prose text-sm text-ink-muted">
            Rules that react to a trigger — an activity completing, a risk level changing, a
            deadline passing — with a testable condition and a set of actions. Nothing here runs
            code a person typed.
          </p>
        </div>
        {mayManage ? (
          <Button type="button" onClick={() => setCreating(true)}>
            <Plus className="size-4" aria-hidden="true" />
            Create Automation
          </Button>
        ) : null}
      </div>

      {counts ? (
        <div className="grid gap-3 sm:grid-cols-3">
          {SHELVES.map((item) => {
            const picked = shelf === item.key;
            return (
              <button
                key={item.key}
                type="button"
                aria-pressed={picked}
                // The badge and the figure are separate elements so they can
                // be styled apart; the accessible name computation joins
                // their text without a space ("Paused1"), so it is spelled
                // out here instead.
                aria-label={`${item.label}: ${counts[item.key as 'active' | 'draft' | 'paused']}`}
                onClick={() => {
                  setShelf(picked ? null : item.key);
                  setPage(1);
                }}
                className={cn(
                  'rounded-card border px-4 py-3 text-left transition-colors',
                  picked ? 'border-action bg-selected/40' : 'border-line hover:bg-sunken/60',
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <Badge variant={item.tone}>{item.label}</Badge>
                  <span className="text-2xl font-semibold tabular-nums">
                    {counts[item.key as 'active' | 'draft' | 'paused']}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ) : null}

      <ListToolbar
        search={search}
        onSearchChange={(value) => {
          setSearch(value);
          setPage(1);
        }}
        placeholder="Automation name"
      />

      {isLoading ? (
        <LoadingState label="Loading automations…" rows={6} />
      ) : error ? (
        <ErrorState
          title="Could not load automations"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={reload}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title={shelf || search ? 'Nothing matches' : 'No automations yet'}
          description={
            shelf || search
              ? 'Every automation is on another shelf, or under another name.'
              : 'Create the first one to react automatically to an activity, a deadline or a risk change.'
          }
          action={
            mayManage && !shelf && !search ? (
              <Button type="button" onClick={() => setCreating(true)}>
                <Plus className="size-4" aria-hidden="true" />
                Create Automation
              </Button>
            ) : undefined
          }
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Automation Name</Th>
                <Th>Module</Th>
                <Th>Trigger</Th>
                <Th>Created On</Th>
                <Th>Created By</Th>
                <Th>Status</Th>
                <Th>
                  <span className="sr-only">Action</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-sunken/40">
                  <Td>
                    <Link
                      href={`/admin/automation/${row.id}`}
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      {row.name}
                    </Link>
                    <p className="text-xs text-ink-muted">
                      v{row.version}
                      {row.is_system ? ' · seeded' : ''}
                    </p>
                  </Td>
                  <Td>
                    <Badge>{AUTOMATION_RECORD_LABEL[automationRecordOf(row.trigger)]}</Badge>
                  </Td>
                  <Td>{AUTOMATION_TRIGGER_LABEL[row.trigger]}</Td>
                  <Td className="whitespace-nowrap tabular-nums">
                    {formatDateTime(row.created_at)}
                  </Td>
                  <Td>{row.created_by_name || '—'}</Td>
                  <Td>
                    <Badge variant={AUTOMATION_RULE_STATUS_VARIANT[row.status]}>
                      {AUTOMATION_RULE_STATUS_LABEL[row.status]}
                    </Badge>
                  </Td>
                  <Td>
                    <RowActions
                      subject={row.name}
                      actions={[
                        {
                          label: 'Edit',
                          icon: Pencil,
                          capability: Capability.automationManage,
                          href: `/admin/automation/${row.id}`,
                        },
                        {
                          label: 'View runs',
                          icon: History,
                          capability: Capability.automationManage,
                          href: `/admin/automation/${row.id}#runs`,
                        },
                      ]}
                    />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}

      {data && data.count > 0 ? (
        <Pagination
          page={data.page}
          totalPages={data.total_pages}
          count={data.count}
          pageSize={data.page_size}
          onPageChange={setPage}
        />
      ) : null}

      <NewRuleDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(id) => {
          setCreating(false);
          router.push(`/admin/automation/${id}`);
        }}
      />
    </div>
  );
}

export default function AutomationRulesPage() {
  return (
    <RequireAuth capability={Capability.automationManage}>
      <AutomationRulesList />
    </RequireAuth>
  );
}
