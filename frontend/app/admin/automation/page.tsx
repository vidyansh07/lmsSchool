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
import { Plus } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
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
  AUTOMATION_TRIGGER_LABEL,
  AUTOMATION_TRIGGER_OPTIONS,
} from "@/lib/labels";
import { formatDateTime } from "@/lib/format";
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
              {AUTOMATION_TRIGGER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
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

function AutomationRulesList() {
  const router = useRouter();
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.automationManage);
  const [page, setPage] = useState(1);
  const { data, error, isLoading, reload } = useApi<Paginated<AutomationRule>>(
    `/api/v1/automation-rules/?page=${page}`,
  );
  const [creating, setCreating] = useState(false);

  const rows = data?.results ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Automation</h1>
          <p className="text-sm text-ink-muted">
            Rules that react to a trigger — an activity completing, a risk level changing, a
            deadline passing — with a testable condition and a set of actions. Nothing here
            runs code a person typed.
          </p>
        </div>
        {mayManage ? (
          <Button type="button" onClick={() => setCreating(true)}>
            <Plus className="size-4" aria-hidden="true" />
            New rule
          </Button>
        ) : null}
      </div>

      {isLoading ? (
        <LoadingState label="Loading automation rules…" rows={6} />
      ) : error ? (
        <ErrorState
          title="Could not load automation rules"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={reload}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No automation rules yet"
          description="Create the first rule to react automatically to an activity, a deadline or a risk change."
          action={
            mayManage ? (
              <Button type="button" onClick={() => setCreating(true)}>
                <Plus className="size-4" aria-hidden="true" />
                New rule
              </Button>
            ) : undefined
          }
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Trigger</Th>
                <Th>Status</Th>
                <Th>Version</Th>
                <Th>Updated</Th>
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
                    {row.is_system ? (
                      <p className="text-xs text-ink-muted">Seeded</p>
                    ) : null}
                  </Td>
                  <Td>{AUTOMATION_TRIGGER_LABEL[row.trigger]}</Td>
                  <Td>
                    <Badge variant={AUTOMATION_RULE_STATUS_VARIANT[row.status]}>
                      {AUTOMATION_RULE_STATUS_LABEL[row.status]}
                    </Badge>
                  </Td>
                  <Td>v{row.version}</Td>
                  <Td>{formatDateTime(row.updated_at)}</Td>
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
