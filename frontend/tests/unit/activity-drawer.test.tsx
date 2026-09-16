/**
 * The activity detail drawer: the transition action bar renders only the
 * buttons legal from the activity's current status (`lib/work.ts`'s
 * `legalTransitions`, transcribed from `apps/work/transitions.py` — there is
 * no field on the detail response itself to drive this from), the complete
 * form surfaces the server's field-level validation errors, and the review
 * action disappears entirely — not merely disables — for the activity's own
 * performer or assignee.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivityDrawer } from "@/components/work/activity-drawer";
import { ApiError } from "@/lib/api";
import type { ActivityDetail } from "@/types/api";

const getActivity = vi.hoisted(() => vi.fn());
const transitionActivity = vi.hoisted(() => vi.fn());
const completeActivity = vi.hoisted(() => vi.fn());
const reviewActivity = vi.hoisted(() => vi.fn());
const deleteActivity = vi.hoisted(() => vi.fn());
const updateActivity = vi.hoisted(() => vi.fn());
vi.mock("@/lib/work", async () => {
  const actual = await vi.importActual<typeof import("@/lib/work")>("@/lib/work");
  return {
    ...actual,
    getActivity,
    transitionActivity,
    completeActivity,
    reviewActivity,
    deleteActivity,
    updateActivity,
  };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock("@/components/auth-provider", () => ({ useAuth }));

function detail(overrides: Partial<ActivityDetail> = {}): ActivityDetail {
  return {
    id: "act-1",
    title: "Mock interview with Asha",
    status: "in_progress",
    priority: "normal",
    planned_at: null,
    due_at: null,
    completed_at: null,
    created_at: "2026-09-16T09:00:00Z",
    student: { id: "s1", name: "Asha Rao", student_id: "STU-001" },
    type: { id: "t1", slug: "mock-interview", name: "Mock Interview", category: "interview" },
    batch: null,
    assigned_to: { id: "trainer-1", name: "Trainer One" },
    created_by: { id: "manager-1", name: "Manager One" },
    counts: { history: 0 },
    performed_by: { id: "trainer-1", name: "Trainer One" },
    reviewed_by: null,
    started_at: null,
    reviewed_at: null,
    duration_minutes: null,
    result: "n/a",
    score: null,
    max_score: null,
    summary: "",
    review_note: "",
    student_visible: true,
    form: null,
    form_values: {},
    history: [],
    parent: null,
    children: [],
    automation_run: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    user: { id: "manager-1", role: "manager", capabilities: [] },
    isLoading: false,
    can: () => false,
  });
});

describe("ActivityDrawer", () => {
  it("renders only the buttons legal from the activity's current status", async () => {
    getActivity.mockResolvedValue(detail({ status: "assigned" }));
    render(<ActivityDrawer activityId="act-1" onOpenChange={vi.fn()} onChanged={vi.fn()} />);

    // `legalTransitions("assigned")` is exactly `["in_progress", "cancelled"]`.
    expect(await screen.findByRole("button", { name: "Start" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assign" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
  });

  it("requires a reason before confirming a reason-required transition", async () => {
    getActivity.mockResolvedValue(detail({ status: "assigned" }));
    render(<ActivityDrawer activityId="act-1" onOpenChange={vi.fn()} onChanged={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    const confirm = await screen.findByRole("button", { name: "Confirm" });
    expect(confirm).toBeDisabled();

    // `getByRole`, not `getByLabelText`: "Reason" is required, and `Field`
    // renders the `*` as an `aria-hidden` sibling that testing-library's
    // plain-text label matcher would include ("Reason*") while the real
    // accessible-name algorithm behind `getByRole` correctly excludes it.
    fireEvent.change(screen.getByRole("textbox", { name: "Reason" }), {
      target: { value: "Duplicate entry" },
    });
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(transitionActivity).toHaveBeenCalledWith("act-1", "cancelled", "Duplicate entry"),
    );
  });

  it("shows the server's field errors on an invalid completion", async () => {
    useAuth.mockReturnValue({
      user: { id: "trainer-1", role: "trainer", capabilities: ["activity.complete"] },
      isLoading: false,
      can: (capability: string) => capability === "activity.complete",
    });
    getActivity.mockResolvedValue(
      detail({
        status: "in_progress",
        form: {
          version: 1,
          fields: [
            {
              id: "f1",
              key: "score",
              label: "Score",
              help: "",
              type: "number",
              required: true,
              order: 0,
              group: "",
              options: null,
              validation: {},
              visible_to_student: true,
              performance_key: "score",
            },
          ],
        },
      }),
    );
    completeActivity.mockRejectedValue(
      new ApiError(400, "validation_error", "The submitted data is invalid.", "req-1", {
        score: ["This field is required."],
      }),
    );

    render(<ActivityDrawer activityId="act-1" onOpenChange={vi.fn()} onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Mark complete" }));

    expect(await screen.findByText("This field is required.")).toBeInTheDocument();
    expect(completeActivity).toHaveBeenCalledTimes(1);
  });

  it("hides the review action when the viewer is the performer", async () => {
    useAuth.mockReturnValue({
      user: { id: "trainer-1", role: "trainer", capabilities: ["activity.review"] },
      isLoading: false,
      can: (capability: string) => capability === "activity.review",
    });
    getActivity.mockResolvedValue(
      detail({
        status: "under_review",
        performed_by: { id: "trainer-1", name: "Trainer One" },
      }),
    );
    render(<ActivityDrawer activityId="act-1" onOpenChange={vi.fn()} onChanged={vi.fn()} />);

    await screen.findByText("Mock interview with Asha");
    expect(screen.queryByText("Review")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("hides the review action when the viewer is the assignee, even without matching the performer", async () => {
    useAuth.mockReturnValue({
      user: { id: "trainer-2", role: "trainer", capabilities: ["activity.review"] },
      isLoading: false,
      can: (capability: string) => capability === "activity.review",
    });
    getActivity.mockResolvedValue(
      detail({
        status: "under_review",
        assigned_to: { id: "trainer-2", name: "Trainer Two" },
        performed_by: { id: "trainer-1", name: "Trainer One" },
      }),
    );
    render(<ActivityDrawer activityId="act-1" onOpenChange={vi.fn()} onChanged={vi.fn()} />);

    await screen.findByText("Mock interview with Asha");
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("shows the review action to a reviewer who is neither the performer nor the assignee", async () => {
    useAuth.mockReturnValue({
      user: { id: "manager-2", role: "manager", capabilities: ["activity.review"] },
      isLoading: false,
      can: (capability: string) => capability === "activity.review",
    });
    getActivity.mockResolvedValue(
      detail({
        status: "under_review",
        assigned_to: { id: "trainer-2", name: "Trainer Two" },
        performed_by: { id: "trainer-1", name: "Trainer One" },
      }),
    );
    render(<ActivityDrawer activityId="act-1" onOpenChange={vi.fn()} onChanged={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(reviewActivity).toHaveBeenCalledWith("act-1", "approved", ""),
    );
  });
});
