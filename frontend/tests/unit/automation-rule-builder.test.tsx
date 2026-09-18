/**
 * The automation rule builder (`/admin/automation/[id]`): the condition
 * editor is locked to the selected trigger's server-declared paths, each
 * action type renders its own typed parameter form, a dry run shows a
 * would-fire/would-not breakdown, and activating requires an explicit
 * confirmation naming the matched-event count.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RuleBuilder } from "@/components/automation/rule-builder";
import { ApiError } from "@/lib/api";
import type { ActivityTypeListResponse } from "@/lib/work";
import type { AutomationDryRunResult, AutomationRuleDetail } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

const testAutomationRule = vi.hoisted(() => vi.fn());
const getAutomationActivationPreview = vi.hoisted(() => vi.fn());
const activateAutomationRule = vi.hoisted(() => vi.fn());
const pauseAutomationRule = vi.hoisted(() => vi.fn());
const updateAutomationRule = vi.hoisted(() => vi.fn());
vi.mock("@/lib/automation", async () => {
  const actual = await vi.importActual<typeof import("@/lib/automation")>("@/lib/automation");
  return {
    ...actual,
    testAutomationRule,
    getAutomationActivationPreview,
    activateAutomationRule,
    pauseAutomationRule,
    updateAutomationRule,
  };
});

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: "admin", capabilities: ["automation.manage"] },
    can: (capability: string) => capability === "automation.manage",
  }),
}));

const RULE: AutomationRuleDetail = {
  id: "rule-1",
  name: "Communication practice after a weak mock",
  description: "",
  trigger: "ACTIVITY_COMPLETED",
  status: "draft",
  version: 1,
  is_system: false,
  branch: null,
  conditions: [],
  actions: [],
  created_by: null,
  updated_by: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

const ACTIVITY_TYPES: ActivityTypeListResponse = {
  results: [
    {
      id: "at-1",
      slug: "mock-interview",
      name: "Mock interview",
      description: "",
      category: "interview",
      allowed_creator_roles: ["trainer"],
      allowed_assignee_roles: ["trainer"],
      visible_to_student: true,
      default_duration_minutes: 30,
      form: null,
      requires_review: false,
      performance_weight: "0.00",
      risk_effect: "none",
      reminder_minutes_before: null,
      next_action: null,
      is_system: true,
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

function mockUseApi(rule: AutomationRuleDetail, reload = vi.fn()) {
  useApi.mockImplementation((path: string) => {
    if (path === `/api/v1/automation-rules/${rule.id}/`) {
      return { data: rule, error: null, isLoading: false, reload };
    }
    if (path === "/api/v1/activity-types/") {
      return { data: ACTIVITY_TYPES, error: null, isLoading: false, reload: vi.fn() };
    }
    throw new Error(`Unexpected useApi path: ${path}`);
  });
  return reload;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RuleBuilder — conditions locked to the selected trigger", () => {
  it("only offers ACTIVITY_COMPLETED's own paths, and clears them on a trigger change", () => {
    mockUseApi(RULE);
    render(<RuleBuilder id="rule-1" />);

    fireEvent.click(screen.getByRole("button", { name: /add condition/i }));
    const pathSelect = screen.getByLabelText("Path") as HTMLSelectElement;
    const optionValues = Array.from(pathSelect.options).map((option) => option.value);
    expect(optionValues).toEqual(
      expect.arrayContaining(["activity.type", "activity.score", "student.risk_level"]),
    );
    expect(optionValues).not.toContain("risk.level");
    expect(optionValues).not.toContain("risk.previous_level");
    // ACTIVITY_COMPLETED allows a custom form.<key> path too.
    expect(screen.getByText("Custom form field…")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Trigger", { exact: false }), {
      target: { value: "RISK_CHANGED" },
    });
    // Switching trigger clears the condition list built against the old one.
    expect(screen.queryByLabelText("Path")).not.toBeInTheDocument();
    expect(
      screen.getByText(/no conditions.*risk level changed/i),
    ).toBeInTheDocument();
  });
});

describe("RuleBuilder — per-action-type parameter forms", () => {
  function addAction() {
    mockUseApi(RULE);
    render(<RuleBuilder id="rule-1" />);
    fireEvent.click(screen.getByRole("button", { name: /add action/i }));
    return screen.getByLabelText("Action") as HTMLSelectElement;
  }

  it("renders create_activity's own fields", () => {
    addAction();
    expect(screen.getByLabelText("Activity type")).toBeInTheDocument();
    expect(screen.getByLabelText("Assign to")).toBeInTheDocument();
    expect(screen.getByLabelText("Due in (days)")).toBeInTheDocument();
  });

  it("renders send_notification's own fields", () => {
    const select = addAction();
    fireEvent.change(select, { target: { value: "send_notification" } });
    expect(screen.getByLabelText("Notification kind")).toBeInTheDocument();
    expect(screen.getByLabelText("Body")).toBeInTheDocument();
  });

  it("renders send_email's own fields", () => {
    const select = addAction();
    fireEvent.change(select, { target: { value: "send_email" } });
    expect(screen.getByLabelText("Template key")).toBeInTheDocument();
  });

  it("renders create_review's own fields", () => {
    const select = addAction();
    fireEvent.change(select, { target: { value: "create_review" } });
    expect(screen.getByLabelText("Reviewer")).toBeInTheDocument();
    expect(screen.getByLabelText("Review type")).toBeInTheDocument();
  });

  it("renders flag_risk's own fields", () => {
    const select = addAction();
    fireEvent.change(select, { target: { value: "flag_risk" } });
    expect(screen.getByLabelText("Level")).toBeInTheDocument();
    expect(screen.getByLabelText("Reason")).toBeInTheDocument();
  });
});

describe("RuleBuilder — dry run", () => {
  it("shows a would-fire/would-not breakdown", async () => {
    mockUseApi(RULE);
    const result: AutomationDryRunResult = [
      {
        object_id: "act-1",
        would_fire: true,
        context: { activity: { type: "mock-interview" }, student: { id: "s-1" } },
      },
      {
        object_id: "act-2",
        would_fire: false,
        context: { activity: { type: "technical-interview" }, student: { id: "s-2" } },
      },
    ];
    testAutomationRule.mockResolvedValue(result);

    render(<RuleBuilder id="rule-1" />);
    fireEvent.click(screen.getByRole("button", { name: /test against recent events/i }));

    await waitFor(() => expect(testAutomationRule).toHaveBeenCalledWith("rule-1"));
    expect(await screen.findByText(/would fire for 1 of 2 recent occurrences/i)).toBeInTheDocument();
    expect(screen.getByText("Would fire")).toBeInTheDocument();
    expect(screen.getByText("Would not fire")).toBeInTheDocument();
    expect(screen.getByText("act-1")).toBeInTheDocument();

    // The breakdown is the occurrence's own context, flattened — visible once expanded.
    fireEvent.click(screen.getAllByText("Occurrence data")[0]!);
    expect(screen.getByText(/activity\.type: "mock-interview"/)).toBeInTheDocument();
  });
});

describe("RuleBuilder — Details field-level errors (Phase R7 Target 2)", () => {
  it("marks Name and Trigger required — the two fields `save()`'s own PATCH payload always sends and the backend rejects blank — but not Description", () => {
    mockUseApi(RULE);
    render(<RuleBuilder id="rule-1" />);

    // Not `getByLabelText` for Name/Trigger: both are now `required`, and
    // `Field` renders the `*` as an `aria-hidden` sibling span, which
    // testing-library's label matcher includes in the label's plain text
    // ("Name*") while the real accessible-name algorithm `getByRole` uses
    // correctly excludes it (see `activity-types-page.test.tsx` for the
    // same note against the same `Field` component).
    expect(screen.getByRole("textbox", { name: "Name" })).toBeRequired();
    expect(screen.getByRole("combobox", { name: "Trigger" })).toBeRequired();
    expect(screen.getByLabelText("Description")).not.toBeRequired();
  });

  it("wires a save failure's field errors onto Name/Trigger/Description instead of only the generic top Alert", async () => {
    mockUseApi(RULE);
    updateAutomationRule.mockRejectedValue(
      new ApiError(400, "validation_error", "The submitted data is invalid.", "req-1", {
        name: ["This field may not be blank."],
        trigger: ["This field may not be blank."],
        description: ["Ensure this field has no more than 2000 characters."],
      }),
    );

    render(<RuleBuilder id="rule-1" />);
    // Any edit marks the form dirty, which is what enables Save changes.
    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(updateAutomationRule).toHaveBeenCalled());
    // Both Name and Trigger show their own message, not just one shared one.
    expect(await screen.findAllByText("This field may not be blank.")).toHaveLength(2);
    expect(
      screen.getByText("Ensure this field has no more than 2000 characters."),
    ).toBeInTheDocument();
  });

  it("still shows a plain top-of-page message when the server error carries no field detail — the pre-existing fallback `fieldErrors` already provides", async () => {
    mockUseApi(RULE);
    updateAutomationRule.mockRejectedValue(
      new ApiError(500, "server_error", "Could not save this rule.", "req-2"),
    );

    render(<RuleBuilder id="rule-1" />);
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "updated" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText("Could not save this rule.")).toBeInTheDocument();
  });
});

describe("RuleBuilder — activation", () => {
  it("shows the matched-event count and only activates on explicit confirmation", async () => {
    mockUseApi(RULE);
    getAutomationActivationPreview.mockResolvedValue(5);
    activateAutomationRule.mockResolvedValue({ ...RULE, status: "active" });

    render(<RuleBuilder id="rule-1" />);
    fireEvent.click(screen.getByRole("button", { name: /^activate$/i }));

    await waitFor(() => expect(getAutomationActivationPreview).toHaveBeenCalledWith("rule-1"));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/matched 5 events in the last 7 days/i)).toBeInTheDocument();

    // Not activated yet — the count is shown, nothing has run.
    expect(activateAutomationRule).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: /^activate$/i }));
    await waitFor(() => expect(activateAutomationRule).toHaveBeenCalledWith("rule-1"));
  });
});
