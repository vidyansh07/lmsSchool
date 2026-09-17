/**
 * Automation Builder (`/api/v1/automation-rules/`, ERP Phase 14, ADR-13).
 *
 * A rule is data, never code a person typed (`docs/erp/AUTOMATION_CATALOG.md`):
 * a trigger, a list of ANDed `{path, op, value}` conditions checked against
 * that trigger's allowlisted context, and a list of `{type, params}` actions
 * run in order when they hold. This client is deliberately thin — every
 * validation (an unknown path, a param shape the action's type does not
 * accept, an author missing the action's permission) is the server's, surfaced
 * through `fieldErrors()`/`errorMessage()` like any other form.
 *
 * This phase's backend (`backend/apps/automation/`) landed in this same
 * worktree while this file was being written, so every endpoint below is
 * checked against its actual `views.py`/`serializers.py`/`services.py`
 * rather than assumed from the catalog or `API_CONTRACTS.md` alone — two
 * things turned out to differ from that document, both noted where they
 * matter:
 *
 * 1. **There is no `GET .../meta/` (or any) endpoint enumerating a trigger's
 *    allowed condition paths.** `apps/automation/evaluator.py::ALLOWED_PATHS`
 *    is the real, single source of truth (`services._validate_rule_shape`
 *    checks a save against it via `path_allowed()`), but nothing serves it.
 *    `AUTOMATION_TRIGGER_PATHS` below is that same table, copied — the one
 *    place in this file that is a duplicate of server code rather than a
 *    client of it, because the alternative (the frontend agent adding a new
 *    backend endpoint to a phase another agent owns, mid-flight) is worse.
 *    If a future edit to `evaluator.py::ALLOWED_PATHS` is not mirrored here,
 *    the builder would offer a path the server then refuses at save time —
 *    a loud, save-time 400, never a silently-accepted bad rule.
 * 2. **Activating a rule has no `{matched_last_7_days}` preview endpoint.**
 *    `AUTOMATION_CATALOG.md`'s builder contract calls for one; this backend
 *    does not build it. `getAutomationActivationPreview()` computes the same
 *    fact honestly from data that *does* exist — `AutomationRun` rows
 *    (`GET .../runs/`, newest first) are only ever created for an occurrence
 *    whose conditions already matched (`services.dispatch`), so counting
 *    this rule's own runs from the last 7 days *is* "how many events it
 *    matched" for a rule that has been active before. A rule activated for
 *    the first time has no run history yet and correctly shows 0 — a true
 *    answer, not a placeholder, though it is admittedly not the forward-
 *    looking estimate the catalog's wording suggests. "Test" (the dry run)
 *    is the tool for that forward-looking question instead.
 */

import { apiFetch, apiMutate } from "./api";
import type {
  AutomationAction,
  AutomationCondition,
  AutomationDryRunResult,
  AutomationRule,
  AutomationRuleDetail,
  AutomationRunRow,
  AutomationTrigger,
  Paginated,
} from "@/types/api";

// ---------------------------------------------------------------------------
// The per-trigger condition-path allowlist. Copied from
// `apps/automation/evaluator.py::ALLOWED_PATHS`/`_STUDENT_PATHS` — see this
// file's own module docstring, point 1, for why there is no endpoint to read
// this from instead.
// ---------------------------------------------------------------------------

const STUDENT_PATHS = [
  "student.id",
  "student.name",
  "student.batch",
  "student.branch",
  "student.trainer",
  "student.counsellor",
  "student.risk_level",
];

export interface TriggerPathInfo {
  paths: string[];
  /** `ACTIVITY_COMPLETED` only: any `form.<key>` path is additionally legal
   *  — the set of keys depends on whichever form is pinned to whichever
   *  activity type a rule is written against, so there is no fixed list of
   *  those to add here. */
  allowsFormPaths: boolean;
}

export const AUTOMATION_TRIGGER_PATHS: Record<AutomationTrigger, TriggerPathInfo> = {
  ACTIVITY_COMPLETED: {
    paths: [
      "activity.id",
      "activity.type",
      "activity.category",
      "activity.score",
      "activity.result",
      "activity.performed_by_role",
      "student.id",
      "student.batch",
      "student.branch",
      "student.risk_level",
    ],
    allowsFormPaths: true,
  },
  ACTIVITY_OVERDUE: {
    paths: [
      "activity.id",
      "activity.type",
      "activity.assigned_to_role",
      "activity.days_overdue",
      ...STUDENT_PATHS,
    ],
    allowsFormPaths: false,
  },
  ASSESSMENT_FAILED: {
    paths: [
      "assessment.id",
      "assessment.percent",
      "assessment.attempt_number",
      "batch.trainer",
      ...STUDENT_PATHS,
    ],
    allowsFormPaths: false,
  },
  ATTENDANCE_THRESHOLD: {
    paths: ["attendance.percent", "attendance.absent_streak", ...STUDENT_PATHS],
    allowsFormPaths: false,
  },
  PROJECT_OVERDUE: {
    paths: ["project.id", "project.days_overdue", ...STUDENT_PATHS],
    allowsFormPaths: false,
  },
  ASSIGNMENT_OVERDUE: {
    paths: ["assignment.id", "assignment.days_overdue", ...STUDENT_PATHS],
    allowsFormPaths: false,
  },
  RISK_CHANGED: {
    paths: ["risk.level", "risk.previous_level", "risk.triggered", "risk.newly_triggered", ...STUDENT_PATHS],
    allowsFormPaths: false,
  },
};

export async function listAutomationRules(page = 1): Promise<Paginated<AutomationRule>> {
  return apiFetch<Paginated<AutomationRule>>(`/api/v1/automation-rules/?page=${page}`);
}

export interface CreateAutomationRulePayload {
  name: string;
  trigger: AutomationTrigger;
  description?: string;
}

export async function createAutomationRule(
  payload: CreateAutomationRulePayload,
): Promise<AutomationRuleDetail> {
  return apiMutate<AutomationRuleDetail>("/api/v1/automation-rules/", {
    method: "POST",
    body: payload,
  });
}

export async function getAutomationRule(id: string): Promise<AutomationRuleDetail> {
  return apiFetch<AutomationRuleDetail>(`/api/v1/automation-rules/${id}/`);
}

export interface UpdateAutomationRulePayload {
  name?: string;
  description?: string;
  trigger?: AutomationTrigger;
  conditions?: AutomationCondition[];
  actions?: AutomationAction[];
}

/** Editable at any status — `AutomationRule.version`'s own docstring notes
 *  it is bumped "on every edit made *after* the rule has left `draft` at
 *  least once", which only makes sense if editing an active/paused rule is
 *  legal (a run always records the rule's version at the moment it ran, so a
 *  later edit changing behaviour is provenance, not a blocked operation).
 *  The builder still treats the trigger itself as fixed once a rule has ever
 *  left `draft`, matching the same "the shape you activated is the shape
 *  that's live" caution `apps/forms` gives a published version's schema. */
export async function updateAutomationRule(
  id: string,
  payload: UpdateAutomationRulePayload,
): Promise<AutomationRuleDetail> {
  return apiMutate<AutomationRuleDetail>(`/api/v1/automation-rules/${id}/`, {
    method: "PATCH",
    body: payload,
  });
}

/** `DELETE /automation-rules/{id}/` (`DeleteReasonSerializer`) — a required
 *  reason, soft delete. Not offered from this phase's own builder screens
 *  (out of the "Builder screen contract" this phase implements), but wired
 *  correctly here for whichever screen surfaces it. */
export async function deleteAutomationRule(id: string, reason: string): Promise<void> {
  await apiMutate<void>(`/api/v1/automation-rules/${id}/`, {
    method: "DELETE",
    body: { reason },
  });
}

/** "Test against a recent event" (`AUTOMATION_CATALOG.md`'s builder
 *  contract) — a dry run against the rule's last 20 real occurrences.
 *  Never executes an action, never writes an `AutomationRun` row
 *  (`services.dry_run`'s own docstring). The real endpoint is
 *  `.../dry-run/`, not `.../test/` — `API_CONTRACTS.md` names the action
 *  "test" but `urls.py` spells the route `dry-run`. */
export async function testAutomationRule(id: string): Promise<AutomationDryRunResult> {
  return apiMutate<AutomationDryRunResult>(`/api/v1/automation-rules/${id}/dry-run/`, {
    method: "POST",
    body: {},
  });
}

export async function activateAutomationRule(id: string): Promise<AutomationRuleDetail> {
  return apiMutate<AutomationRuleDetail>(`/api/v1/automation-rules/${id}/activate/`, {
    method: "POST",
    body: {},
  });
}

export async function pauseAutomationRule(id: string, reason = ""): Promise<AutomationRuleDetail> {
  return apiMutate<AutomationRuleDetail>(`/api/v1/automation-rules/${id}/pause/`, {
    method: "POST",
    body: { reason },
  });
}

export async function listAutomationRuns(
  id: string,
  page = 1,
): Promise<Paginated<AutomationRunRow>> {
  return apiFetch<Paginated<AutomationRunRow>>(
    `/api/v1/automation-rules/${id}/runs/?page=${page}`,
  );
}

/** See this file's own module docstring, point 2: there is no server-side
 *  preview endpoint, so this counts the rule's own `AutomationRun` rows
 *  (ordered newest-first, per `AutomationRun.Meta.ordering`) from the last 7
 *  days — real history, not an estimate. Paginates only as far as it has to:
 *  it stops the moment a page's rows fall out of the 7-day window, and gives
 *  up (returning what it has counted so far) after `MAX_PAGES` — a rule
 *  matching that many times a week has made its point without a person
 *  waiting on an unbounded fetch for one confirmation dialog. */
export async function getAutomationActivationPreview(id: string): Promise<number> {
  const MAX_PAGES = 20;
  const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
  let matched = 0;
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const batch = await listAutomationRuns(id, page);
    for (const run of batch.results) {
      if (new Date(run.created_at).getTime() < cutoff) return matched;
      matched += 1;
    }
    if (!batch.next) break;
  }
  return matched;
}

// --- Condition value parsing -------------------------------------------

/** Operators whose value is a list (comma-separated in the builder's input)
 *  rather than a single scalar. */
export function operatorTakesList(op: AutomationCondition["op"]): boolean {
  return op === "in" || op === "not_in";
}

/** A best-effort literal from typed text: numbers and `true`/`false` parse to
 *  their real type so `eq`/`lt`/… compare correctly server-side; anything
 *  else stays a string. Conditions are literals only (the catalog is
 *  explicit), so there is never an expression to evaluate here. */
export function parseConditionLiteral(raw: string): string | number | boolean {
  const trimmed = raw.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (trimmed !== "" && !Number.isNaN(Number(trimmed))) return Number(trimmed);
  return raw;
}

/** Renders a condition value back to text for the builder's input — a plain
 *  scalar for `eq`/`lt`/…, comma-joined for `in`/`not_in`'s list editor. */
export function conditionValueToText(value: AutomationCondition["value"]): string {
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

export function parseConditionList(raw: string): (string | number)[] {
  return raw
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0)
    .map((entry) => {
      const literal = parseConditionLiteral(entry);
      return typeof literal === "boolean" ? entry : literal;
    });
}

/**
 * A strategy is one of the catalog's own named keywords, resolved to a real
 * person by `apps.automation.resolve.resolve_user` — never a role check this
 * app re-derives. Each action's own row in `AUTOMATION_CATALOG.md`'s
 * "Actions" table names exactly which strategies it accepts; these lists are
 * that same fixed set, one per action, plus the literal fallback (a user id,
 * or for `send_notification`/`send_email`/`send_whatsapp` a role slug or a
 * bare address) every one of them also allows through free text.
 */
export const ASSIGN_TO_STRATEGIES = [
  { value: "same_assignee", label: "The same person already assigned" },
  { value: "batch_trainer", label: "The batch's trainer" },
  { value: "counsellor", label: "The enrolment's counsellor" },
  { value: "creator", label: "Whoever created the triggering activity" },
];

/** `send_notification`/`send_email`/`send_whatsapp`'s `to` also accepts any
 *  role slug (a role-wide broadcast) — those six come from `ROLE_OPTIONS`
 *  (`lib/labels.ts`); this is only the one strategy that is not also a role. */
export const NOTIFICATION_TO_STRATEGIES = [
  { value: "assignee", label: "The activity's assignee" },
];

export const REVIEWER_STRATEGIES = [{ value: "manager", label: "A manager at the branch" }];
