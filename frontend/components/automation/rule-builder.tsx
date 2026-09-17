"use client";

/**
 * One `AutomationRule`'s builder screen (`docs/erp/AUTOMATION_CATALOG.md`
 * "Builder screen contract"): trigger, conditions, actions, Test (a dry
 * run, never destructive) and Save/Activate/Pause — one page, the same
 * "sections stacked on a single detail route" shape `components/forms/
 * form-detail.tsx` uses for a version's field editor, not a modal wizard,
 * since every section here (like that one) is small enough to see at once
 * and a person moves back and forth between them rather than through them
 * in one direction.
 */

import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Confirm } from "@/components/confirm";
import { ErrorState, LoadingState } from "@/components/states";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { ActionEditor } from "@/components/automation/action-editor";
import { ConditionEditor } from "@/components/automation/condition-editor";
import { useApi } from "@/hooks/use-api";
import {
  activateAutomationRule,
  AUTOMATION_TRIGGER_PATHS,
  getAutomationActivationPreview,
  pauseAutomationRule,
  testAutomationRule,
  updateAutomationRule,
} from "@/lib/automation";
import { errorMessage } from "@/lib/api";
import { Capability, can } from "@/lib/capabilities";
import {
  AUTOMATION_RULE_STATUS_LABEL,
  AUTOMATION_RULE_STATUS_VARIANT,
  AUTOMATION_TRIGGER_LABEL,
  AUTOMATION_TRIGGER_OPTIONS,
} from "@/lib/labels";
import { formatDateTime } from "@/lib/format";
import type { ActivityTypeListResponse } from "@/lib/work";
import type {
  AutomationAction,
  AutomationCondition,
  AutomationDryRunResult,
  AutomationRuleDetail,
  AutomationTrigger,
} from "@/types/api";

export function RuleBuilder({ id }: { id: string }) {
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.automationManage);

  const { data: rule, error, isLoading, reload } = useApi<AutomationRuleDetail>(
    `/api/v1/automation-rules/${id}/`,
  );
  const { data: activityTypeData } = useApi<ActivityTypeListResponse>("/api/v1/activity-types/");

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [trigger, setTrigger] = useState<AutomationTrigger>("ACTIVITY_COMPLETED");
  const [conditions, setConditions] = useState<AutomationCondition[]>([]);
  const [actions, setActions] = useState<AutomationAction[]>([]);
  const [dirty, setDirty] = useState(false);

  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);

  const [dryRun, setDryRun] = useState<AutomationDryRunResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [testFailure, setTestFailure] = useState<string | null>(null);

  const [activationPreview, setActivationPreview] = useState<number | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  // Re-seed the editable copy every time a fresh rule arrives from the
  // server — on first load, and again after Save/Activate/Pause's own
  // `reload()` — so the screen always edits from the server's own truth
  // rather than accumulating a divergent local draft across mutations.
  // Reset during render, not inside an effect: `useApi` hands back a new
  // object on every fetch, so reference inequality alone means "this is a
  // fetch this screen has not seeded from yet" — the same pattern `hooks/
  // use-api.ts` and `components/forms/form-detail.tsx` use for the same
  // reason (a synchronous `setState` in an effect body causes a cascading
  // render React's lint flags).
  const [seededRule, setSeededRule] = useState<AutomationRuleDetail | null>(null);
  if (rule && rule !== seededRule) {
    setName(rule.name);
    setDescription(rule.description);
    setTrigger(rule.trigger);
    setConditions(rule.conditions);
    setActions(rule.actions);
    setDirty(false);
    setDryRun(null);
    setSeededRule(rule);
  }

  const triggerMeta = AUTOMATION_TRIGGER_PATHS[trigger];
  const activityTypeOptions = (activityTypeData?.results ?? [])
    .filter((type) => type.status === "active")
    .map((type) => ({ slug: type.slug, name: type.name }));

  // A rule's trigger governs which condition paths are even legal, so
  // changing it invalidates whatever conditions were written against the
  // old one — cleared here rather than left to fail the next save with a
  // confusing "unknown path" error. Restricted to `draft`: once a rule has
  // been activated at least once, the shape it was confirmed against stays
  // fixed (the same caution a published form version's schema gets).
  const canEditTrigger = rule?.status === "draft";

  if (isLoading) return <LoadingState label="Loading the rule…" rows={8} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load this rule"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={reload}
      />
    );
  }
  if (!rule) {
    return (
      <ErrorState
        title="Rule not found"
        message="This automation rule does not exist, or you may not have access to it."
      />
    );
  }

  async function save() {
    setIsSaving(true);
    setFailure(null);
    try {
      await updateAutomationRule(id, { name, description, trigger, conditions, actions });
      setNotice("Changes saved.");
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, "Could not save this rule."));
    } finally {
      setIsSaving(false);
    }
  }

  async function runTest() {
    setIsTesting(true);
    setTestFailure(null);
    setDryRun(null);
    try {
      const result = await testAutomationRule(id);
      setDryRun(result);
    } catch (cause) {
      setTestFailure(errorMessage(cause, "Could not run the test."));
    } finally {
      setIsTesting(false);
    }
  }

  async function openActivateConfirm() {
    setIsLoadingPreview(true);
    setFailure(null);
    try {
      const matched = await getAutomationActivationPreview(id);
      setActivationPreview(matched);
    } catch (cause) {
      setFailure(errorMessage(cause, "Could not check how often this rule matches."));
    } finally {
      setIsLoadingPreview(false);
    }
  }

  async function confirmActivate() {
    setIsTransitioning(true);
    setFailure(null);
    try {
      await activateAutomationRule(id);
      setNotice("Rule activated.");
      setActivationPreview(null);
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, "Could not activate this rule."));
      setActivationPreview(null);
    } finally {
      setIsTransitioning(false);
    }
  }

  async function pause() {
    setIsTransitioning(true);
    setFailure(null);
    try {
      await pauseAutomationRule(id);
      setNotice("Rule paused.");
      reload();
    } catch (cause) {
      setFailure(errorMessage(cause, "Could not pause this rule."));
    } finally {
      setIsTransitioning(false);
    }
  }

  return (
    <div className="animate-rise-in space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{rule.name}</h1>
            <Badge variant={AUTOMATION_RULE_STATUS_VARIANT[rule.status]}>
              {AUTOMATION_RULE_STATUS_LABEL[rule.status]}
            </Badge>
            {rule.is_system ? <Badge variant="neutral">Seeded</Badge> : null}
          </div>
          <p className="text-sm text-muted-foreground">
            v{rule.version} · updated {formatDateTime(rule.updated_at)}
          </p>
        </div>
        {mayManage ? (
          <div className="flex flex-wrap gap-2">
            {rule.status === "active" ? (
              <Button type="button" variant="outline" disabled={isTransitioning} onClick={() => void pause()}>
                {isTransitioning ? "Pausing…" : "Pause"}
              </Button>
            ) : (
              <Button
                type="button"
                variant="outline"
                disabled={dirty || isTransitioning || isLoadingPreview}
                onClick={() => void openActivateConfirm()}
              >
                {isLoadingPreview ? "Checking…" : "Activate"}
              </Button>
            )}
            <Button type="button" disabled={!dirty || isSaving} onClick={() => void save()}>
              {isSaving ? "Saving…" : "Save changes"}
            </Button>
          </div>
        ) : null}
      </div>

      {notice ? <Alert variant="success">{notice}</Alert> : null}
      {failure ? <Alert variant="error">{failure}</Alert> : null}
      {dirty ? (
        <Alert variant="warning">
          Unsaved changes — save before testing or activating so either one reflects what you
          see here.
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Name" htmlFor="rule-name">
            <Input
              id="rule-name"
              disabled={!mayManage}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setDirty(true);
              }}
            />
          </Field>
          <Field
            label="Trigger"
            htmlFor="rule-trigger"
            hint={
              canEditTrigger
                ? "Changing this clears the conditions below."
                : "Fixed once a rule has been activated."
            }
          >
            <Select
              id="rule-trigger"
              disabled={!mayManage || !canEditTrigger}
              value={trigger}
              onChange={(event) => {
                setTrigger(event.target.value as AutomationTrigger);
                setConditions([]);
                setDirty(true);
              }}
            >
              {AUTOMATION_TRIGGER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Description" htmlFor="rule-description" className="sm:col-span-2">
            <Textarea
              id="rule-description"
              rows={2}
              disabled={!mayManage}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
                setDirty(true);
              }}
            />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Conditions</CardTitle>
        </CardHeader>
        <CardContent>
          <ConditionEditor
            conditions={conditions}
            triggerMeta={triggerMeta}
            triggerLabel={AUTOMATION_TRIGGER_LABEL[trigger]}
            disabled={!mayManage}
            onChange={(next) => {
              setConditions(next);
              setDirty(true);
            }}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <ActionEditor
            actions={actions}
            activityTypeOptions={activityTypeOptions}
            disabled={!mayManage}
            onChange={(next) => {
              setActions(next);
              setDirty(true);
            }}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle>Test</CardTitle>
          <Button type="button" variant="outline" size="sm" disabled={dirty || isTesting} onClick={() => void runTest()}>
            {isTesting ? "Testing…" : "Test against recent events"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            A dry run against this trigger&rsquo;s most recent occurrences. Nothing here is
            executed — no activity created, no notification sent.
          </p>
          {testFailure ? <Alert variant="error">{testFailure}</Alert> : null}
          {dryRun ? (
            <DryRunResults result={dryRun} conditionPaths={conditions.map((c) => c.path)} />
          ) : null}
        </CardContent>
      </Card>

      <Confirm
        open={activationPreview !== null}
        title={`Activate "${rule.name}"?`}
        description={`This rule has matched ${activationPreview ?? 0} event${
          activationPreview === 1 ? "" : "s"
        } in the last 7 days (0 if it has never been active before). Once active, every action listed above runs automatically the next time it matches — use Test above to see how it reads against occurrences right now.`}
        confirmLabel="Activate"
        confirmVariant="primary"
        isConfirming={isTransitioning}
        onConfirm={() => void confirmActivate()}
        onCancel={() => setActivationPreview(null)}
      />
    </div>
  );
}

/** Flattens `{activity: {type: "x", score: 5}, student: {...}}` into
 *  `["activity.type: x", "activity.score: 5", ...]` — the same dotted-path
 *  spelling a condition's own `path` uses, so a row here reads directly
 *  against what someone just wrote above it. */
function flattenContext(context: Record<string, unknown>, prefix = ""): [string, unknown][] {
  const rows: [string, unknown][] = [];
  for (const [key, value] of Object.entries(context)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      rows.push(...flattenContext(value as Record<string, unknown>, path));
    } else {
      rows.push([path, value]);
    }
  }
  return rows;
}

function DryRunResults({
  result,
  conditionPaths,
}: {
  result: AutomationDryRunResult;
  /** The rule's own condition paths, highlighted in the context breakdown so
   *  the ones that decided `would_fire` are easy to find among the rest. */
  conditionPaths: string[];
}) {
  const wouldFireCount = result.filter((event) => event.would_fire).length;

  if (result.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No recent occurrences of this trigger to test against yet.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">
        Would fire for {wouldFireCount} of {result.length} recent occurrence
        {result.length === 1 ? "" : "s"}.
      </p>
      <ul className="space-y-2">
        {result.map((event) => (
          <li key={event.object_id} className="rounded-md border border-border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-mono text-xs text-muted-foreground">{event.object_id}</span>
              <Badge variant={event.would_fire ? "success" : "neutral"}>
                {event.would_fire ? "Would fire" : "Would not fire"}
              </Badge>
            </div>
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-muted-foreground">
                Occurrence data
              </summary>
              <ul className="mt-1 space-y-1 pl-4 text-xs">
                {flattenContext(event.context).map(([path, value]) => (
                  <li
                    key={path}
                    className={conditionPaths.includes(path) ? "font-medium" : "text-muted-foreground"}
                  >
                    {path}: {JSON.stringify(value)}
                  </li>
                ))}
              </ul>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}
