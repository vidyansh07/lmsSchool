"use client";

/**
 * The Policy Builder (ERP Phase 3, ADR-04): category list on the left, that
 * category's keys on the right, each showing its value in force, the schema
 * default, who last changed it and when, and a link to its full history.
 *
 * User: superadmin/admin manage; a branch-scoped manager (`policy.view`
 * only) sees the same screen read-only. Primary action: edit a key's value.
 * Secondary actions: reset a key to its schema default; open its history.
 * A critical key (a red "Critical" tag) additionally needs a fresh step-up
 * and, on edit, typing the key exactly into a confirmation field — the same
 * step-up contract `components/roles/permission-matrix.tsx` uses for
 * locking a grant.
 *
 * API on load: `GET /policies/` (every key, institution-wide — D-135: a
 * branch-override picker is not part of this first version, since the
 * design brief for this screen names none). On edit: `PUT
 * /policies/{category}/{key}/`. On reset: `DELETE
 * /policies/{category}/{key}/`. On opening History: `GET
 * /policies/{category}/{key}/history/`, paginated.
 *
 * States: loading (skeleton), error (retry), empty (no schema keys — not
 * expected, guarded anyway), denied (`RequireAuth`'s capability gate),
 * success (the two-pane list). A key never 404s from here: every row comes
 * from the server's own schema listing, never a guessed id.
 *
 * Mobile: the category list becomes a horizontally scrolling strip above
 * the keys instead of a sidebar.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  History as HistoryIcon,
  Pencil,
  RotateCcw,
  ShieldAlert,
} from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { RequireAuth } from "@/components/require-auth";
import {
  isStepUpRequired,
  StepUpDialog,
} from "@/components/roles/step-up-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { Switch } from "@/components/ui/switch";
import { Table, TableWrapper, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { ApiError, errorMessage, fieldErrors } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import { formatDateTime, UNKNOWN } from "@/lib/format";
import { POLICY_CATEGORY_LABEL } from "@/lib/labels";
import {
  formatPolicyValue,
  getPolicyHistory,
  PERFORMANCE_COMPONENTS,
  PERFORMANCE_COMPONENT_LABEL,
  POLICY_CHOICES,
  policyFieldKind,
  resetPolicy,
  updatePolicy,
  type PolicyFieldKind,
} from "@/lib/policies";
import type {
  Paginated,
  PolicyCategory,
  PolicyEntry,
  PolicyValue,
  PolicyVersion,
} from "@/types/api";

const CATEGORY_ORDER: PolicyCategory[] = [
  "authentication",
  "password",
  "session",
  "risk",
  "performance",
  "communication",
  "export",
  "deletion",
  "approval",
  "file_upload",
  "notification",
];

function PolicyRow({
  entry,
  mayManage,
  onEdit,
  onReset,
  onHistory,
}: {
  entry: PolicyEntry;
  mayManage: boolean;
  onEdit: (entry: PolicyEntry) => void;
  onReset: (entry: PolicyEntry) => void;
  onHistory: (entry: PolicyEntry) => void;
}) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-start justify-between gap-4 pt-5">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">
              {entry.description || entry.key}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {entry.category}.{entry.key}
            </span>
            {entry.critical ? (
              <Badge variant="error">
                <ShieldAlert className="mr-1 size-3" aria-hidden="true" />
                Critical
              </Badge>
            ) : null}
            <Badge variant={entry.is_default ? "neutral" : "success"}>
              {entry.is_default ? "Default" : "Custom"}
            </Badge>
          </div>
          <p className="text-sm">
            Value:{" "}
            <span className="font-medium">
              {formatPolicyValue(entry.value)}
            </span>
            {!entry.is_default ? (
              <span className="text-muted-foreground">
                {" "}
                · Default: {formatPolicyValue(entry.default)}
              </span>
            ) : null}
          </p>
          <p className="text-xs text-muted-foreground">
            {entry.is_default
              ? "Never changed."
              : `Changed by ${entry.updated_by_name ?? UNKNOWN} · ${formatDateTime(entry.updated_at)}`}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onHistory(entry)}
          >
            <HistoryIcon className="size-3.5" aria-hidden="true" />
            History
          </Button>
          {mayManage ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onEdit(entry)}
            >
              <Pencil className="size-3.5" aria-hidden="true" />
              Edit
            </Button>
          ) : null}
          {mayManage && !entry.is_default ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onReset(entry)}
            >
              <RotateCcw className="size-3.5" aria-hidden="true" />
              Reset
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function EditDialog({
  entry,
  retryToken,
  onClose,
  onStepUpRequired,
  onSaved,
}: {
  entry: PolicyEntry;
  /** Bumped once a step-up this dialog asked for succeeds, so the save that
   *  was refused for freshness is retried exactly once (ADR-05/D-134). */
  retryToken: number;
  onClose: () => void;
  onStepUpRequired: () => void;
  onSaved: (message: string) => void;
}) {
  const kind: PolicyFieldKind = policyFieldKind(
    entry.category,
    entry.key,
    entry.value,
  );
  const [formValue, setFormValue] = useState(() =>
    kind === "boolean" || kind === "weights" ? "" : String(entry.value),
  );
  const [formBool, setFormBool] = useState(() =>
    kind === "boolean" ? (entry.value as boolean) : false,
  );
  const [formWeights, setFormWeights] = useState<Record<string, string>>(() =>
    kind === "weights" ? { ...(entry.value as Record<string, string>) } : {},
  );
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  function currentValue(): PolicyValue {
    if (kind === "integer") return Number.parseInt(formValue, 10);
    if (kind === "decimal" || kind === "choice") return formValue;
    if (kind === "boolean") return formBool;
    return formWeights;
  }

  async function save() {
    setIsSaving(true);
    setErrors({});
    setFormError(null);
    try {
      await updatePolicy(entry.category, entry.key, {
        value: currentValue(),
        reason: reason.trim(),
        confirm: entry.critical ? confirm.trim() : undefined,
      });
      onSaved(`"${entry.category}.${entry.key}" updated.`);
    } catch (cause) {
      if (isStepUpRequired(cause)) {
        onStepUpRequired();
        return;
      }
      const fields = fieldErrors(cause);
      setErrors(fields);
      setFormError(
        Object.keys(fields).length === 0
          ? errorMessage(cause, "That could not be saved.")
          : (fields.__all__ ?? null),
      );
    } finally {
      setIsSaving(false);
    }
  }

  // Retries the save exactly once after a step-up this dialog asked for
  // succeeds. The ref holds the token this instance last saw so a dialog
  // that opens after some *other* action already bumped it does not retry
  // on mount.
  const seenRetryToken = useRef(retryToken);
  useEffect(() => {
    if (retryToken !== seenRetryToken.current) {
      seenRetryToken.current = retryToken;
      void save();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryToken]);

  const confirmOk = !entry.critical || confirm.trim() === entry.key;
  const valueOk =
    kind !== "integer" && kind !== "decimal" ? true : formValue.trim() !== "";
  const canSave = reason.trim().length > 0 && confirmOk && valueOk && !isSaving;

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <DialogHeader>
            <DialogTitle>
              Edit {entry.category}.{entry.key}
            </DialogTitle>
            <DialogDescription>{entry.description}</DialogDescription>
          </DialogHeader>
          {formError ? <Alert variant="error">{formError}</Alert> : null}

          {kind === "integer" || kind === "decimal" ? (
            <Field
              label="New value"
              htmlFor="policy-value"
              error={errors.value}
            >
              <Input
                id="policy-value"
                type="number"
                step={kind === "decimal" ? "0.01" : "1"}
                value={formValue}
                onChange={(event) => setFormValue(event.target.value)}
              />
            </Field>
          ) : null}

          {kind === "choice" ? (
            <Field
              label="New value"
              htmlFor="policy-value"
              error={errors.value}
            >
              <Select
                id="policy-value"
                value={formValue}
                onChange={(event) => setFormValue(event.target.value)}
              >
                {(POLICY_CHOICES[`${entry.category}.${entry.key}`] ?? []).map(
                  (choice) => (
                    <option key={choice} value={choice}>
                      {choice}
                    </option>
                  ),
                )}
              </Select>
            </Field>
          ) : null}

          {kind === "boolean" ? (
            <div className="space-y-1.5">
              <label
                htmlFor="policy-value"
                className="block text-sm font-medium"
              >
                New value
              </label>
              <div className="flex items-center gap-2">
                <Switch
                  id="policy-value"
                  checked={formBool}
                  onCheckedChange={setFormBool}
                  aria-label="New value"
                />
                <span className="text-sm">{formBool ? "Yes" : "No"}</span>
              </div>
              {errors.value ? (
                <p className="text-xs text-destructive">{errors.value}</p>
              ) : null}
            </div>
          ) : null}

          {kind === "weights" ? (
            <div className="space-y-3">
              {PERFORMANCE_COMPONENTS.map((component) => (
                <Field
                  key={component}
                  label={PERFORMANCE_COMPONENT_LABEL[component]}
                  htmlFor={`weight-${component}`}
                >
                  <Input
                    id={`weight-${component}`}
                    type="number"
                    step="0.01"
                    value={formWeights[component] ?? ""}
                    onChange={(event) =>
                      setFormWeights({
                        ...formWeights,
                        [component]: event.target.value,
                      })
                    }
                  />
                </Field>
              ))}
              {errors.value ? (
                <p className="text-xs text-destructive">{errors.value}</p>
              ) : null}
            </div>
          ) : null}

          <Field label="Reason" htmlFor="policy-reason" error={errors.reason}>
            <Input
              id="policy-reason"
              required
              maxLength={300}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Why is this changing?"
            />
          </Field>

          {entry.critical ? (
            <Field
              label={`Type "${entry.key}" to confirm`}
              htmlFor="policy-confirm"
              error={errors.confirm}
              hint="This is a critical setting. A fresh step-up is also required."
            >
              <Input
                id="policy-confirm"
                required
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
              />
            </Field>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave}>
              {isSaving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ResetDialog({
  entry,
  retryToken,
  onClose,
  onStepUpRequired,
  onReset,
}: {
  entry: PolicyEntry;
  /** See `EditDialog`'s prop of the same name. */
  retryToken: number;
  onClose: () => void;
  onStepUpRequired: () => void;
  onReset: (message: string) => void;
}) {
  const [failure, setFailure] = useState<string | null>(null);
  const [isResetting, setIsResetting] = useState(false);

  async function confirm() {
    setIsResetting(true);
    setFailure(null);
    try {
      await resetPolicy(entry.category, entry.key);
      onReset(`"${entry.category}.${entry.key}" reset to its default.`);
    } catch (cause) {
      if (isStepUpRequired(cause)) {
        onStepUpRequired();
        return;
      }
      setFailure(errorMessage(cause, "That could not be reset."));
    } finally {
      setIsResetting(false);
    }
  }

  const seenRetryToken = useRef(retryToken);
  useEffect(() => {
    if (retryToken !== seenRetryToken.current) {
      seenRetryToken.current = retryToken;
      void confirm();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryToken]);

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Reset {entry.category}.{entry.key}?
          </DialogTitle>
          <DialogDescription>
            Returns to the schema default, {formatPolicyValue(entry.default)}.
            The current value, {formatPolicyValue(entry.value)}, stays in its
            history.
          </DialogDescription>
        </DialogHeader>
        {failure ? <Alert variant="error">{failure}</Alert> : null}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Keep it
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={isResetting}
            onClick={() => void confirm()}
          >
            {isResetting ? "Resetting…" : "Reset to default"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function HistoryDialog({
  entry,
  onClose,
}: {
  entry: PolicyEntry;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  // Reset is a render-time state update keyed on the request's identity,
  // not a `setState` inside the effect body: a synchronous `setState` in an
  // effect causes a cascading render, which `react-hooks/set-state-in-effect`
  // (rightly) flags. Same shape as `hooks/use-api.ts`.
  const requestKey = `${entry.category}/${entry.key}#${page}`;
  const [state, setState] = useState<{
    data: Paginated<PolicyVersion> | null;
    error: ApiError | null;
    isLoading: boolean;
    requestKey: string;
  }>({ data: null, error: null, isLoading: true, requestKey });

  if (state.requestKey !== requestKey) {
    setState({ data: null, error: null, isLoading: true, requestKey });
  }

  useEffect(() => {
    let cancelled = false;
    getPolicyHistory(entry.category, entry.key, { page })
      .then((result) => {
        if (!cancelled)
          setState({ data: result, error: null, isLoading: false, requestKey });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const asApiError =
          cause instanceof ApiError
            ? cause
            : new ApiError(0, "unknown_error", "The request failed.", "");
        setState({
          data: null,
          error: asApiError,
          isLoading: false,
          requestKey,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [entry, page, requestKey]);

  const { data, error, isLoading } = state;

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>
            History: {entry.category}.{entry.key}
          </DialogTitle>
          <DialogDescription>
            Every value this key has held, newest first — kept even across a
            reset.
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <LoadingState label="Loading history…" rows={3} />
        ) : error ? (
          <ErrorState
            title="Could not load the history"
            message={error.message}
            requestId={error.requestId || undefined}
          />
        ) : !data || data.results.length === 0 ? (
          <EmptyState
            title="No history yet"
            description="This key has never been changed."
          />
        ) : (
          <div className="space-y-3">
            <TableWrapper>
              <Table>
                <thead>
                  <tr>
                    <Th>Version</Th>
                    <Th>Value</Th>
                    <Th>Changed by</Th>
                    <Th>Reason</Th>
                    <Th>When</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((row) => (
                    <tr key={row.id}>
                      <Td className="tabular-nums">{row.version}</Td>
                      <Td>{formatPolicyValue(row.value)}</Td>
                      <Td>{row.changed_by_name ?? UNKNOWN}</Td>
                      <Td>{row.reason || "—"}</Td>
                      <Td>{formatDateTime(row.created_at)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrapper>
            {data.total_pages > 1 ? (
              <div className="flex items-center justify-between text-sm">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!data.previous}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                >
                  Previous
                </Button>
                <span className="text-muted-foreground">
                  Page {data.page} of {data.total_pages}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!data.next}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Next
                </Button>
              </div>
            ) : null}
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PoliciesScreen() {
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.policyManage);
  const { data, error, isLoading, reload } =
    useApi<PolicyEntry[]>("/api/v1/policies/");

  const [category, setCategory] = useState<PolicyCategory>(
    CATEGORY_ORDER[0] ?? "authentication",
  );
  const [editing, setEditing] = useState<PolicyEntry | null>(null);
  const [resetting, setResetting] = useState<PolicyEntry | null>(null);
  const [historyFor, setHistoryFor] = useState<PolicyEntry | null>(null);
  // A single shared step-up dialog for both edit and reset (only one of
  // those can be open at a time): confirming it bumps `retryToken`, which
  // whichever dialog is mounted uses to retry its own refused call once.
  const [stepUpOpen, setStepUpOpen] = useState(false);
  const [retryToken, setRetryToken] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const map = new Map<PolicyCategory, PolicyEntry[]>();
    for (const cat of CATEGORY_ORDER) map.set(cat, []);
    for (const entry of data ?? []) map.get(entry.category)?.push(entry);
    return map;
  }, [data]);

  const keysForCategory = grouped.get(category) ?? [];

  function afterEdit(message: string) {
    setEditing(null);
    setNotice(message);
    reload();
  }

  function afterReset(message: string) {
    setResetting(null);
    setNotice(message);
    reload();
  }

  if (isLoading) return <LoadingState label="Loading policies…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load policies"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={reload}
      />
    );
  }
  if (!data || data.length === 0) {
    return (
      <EmptyState
        title="No policies"
        description="The policy schema has not been seeded."
      />
    );
  }

  return (
    <div className="animate-rise-in space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Policies</h1>
        <p className="text-sm text-muted-foreground">
          Institution-wide settings outside academic rules. A critical key needs
          a fresh step-up and typing its name to change.
        </p>
      </div>

      {notice ? <Alert variant="success">{notice}</Alert> : null}

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav
          aria-label="Policy categories"
          className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0"
        >
          {CATEGORY_ORDER.map((cat) => {
            const items = grouped.get(cat) ?? [];
            const customCount = items.filter(
              (entry) => !entry.is_default,
            ).length;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setCategory(cat)}
                aria-current={category === cat ? "page" : undefined}
                className={`flex shrink-0 items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm whitespace-nowrap ${
                  category === cat
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted"
                }`}
              >
                <span>{POLICY_CATEGORY_LABEL[cat]}</span>
                {customCount > 0 ? (
                  <Badge variant={category === cat ? "neutral" : "success"}>
                    {customCount}
                  </Badge>
                ) : null}
              </button>
            );
          })}
        </nav>

        <div className="space-y-3">
          {keysForCategory.length === 0 ? (
            <EmptyState title="No keys in this category" />
          ) : (
            keysForCategory.map((entry) => (
              <PolicyRow
                key={entry.key}
                entry={entry}
                mayManage={mayManage}
                onEdit={setEditing}
                onReset={setResetting}
                onHistory={setHistoryFor}
              />
            ))
          )}
        </div>
      </div>

      {editing ? (
        <EditDialog
          entry={editing}
          retryToken={retryToken}
          onClose={() => setEditing(null)}
          onStepUpRequired={() => setStepUpOpen(true)}
          onSaved={afterEdit}
        />
      ) : null}

      {resetting ? (
        <ResetDialog
          entry={resetting}
          retryToken={retryToken}
          onClose={() => setResetting(null)}
          onStepUpRequired={() => setStepUpOpen(true)}
          onReset={afterReset}
        />
      ) : null}

      {historyFor ? (
        <HistoryDialog entry={historyFor} onClose={() => setHistoryFor(null)} />
      ) : null}

      <StepUpDialog
        open={stepUpOpen}
        onConfirmed={() => {
          setStepUpOpen(false);
          setRetryToken((token) => token + 1);
        }}
        onCancel={() => setStepUpOpen(false)}
      />
    </div>
  );
}

export default function PoliciesPage() {
  return (
    <RequireAuth capability={Capability.policyView}>
      <PoliciesScreen />
    </RequireAuth>
  );
}
