/**
 * `app/admin/activity-types/page.tsx` (Phase R7 Target 3): the ~15-field
 * dialog now stages the non-essential fields behind three `<details>`
 * sections instead of rendering everything at once. Coverage: a new type
 * starts with those sections collapsed, editing an existing one starts with
 * them open, and a server-side field error forces its own section open even
 * for a brand-new type.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ActivityTypesPage from "@/app/admin/activity-types/page";
import { createActivityType } from "@/lib/work";
import { ApiError } from "@/lib/api";
import type { ActivityType } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

vi.mock("@/lib/work", async () => {
  const actual = await vi.importActual<typeof import("@/lib/work")>("@/lib/work");
  return { ...actual, createActivityType: vi.fn() };
});

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: "admin", capabilities: ["activity_type.manage"] },
    can: () => true,
  }),
}));
vi.mock("@/components/require-auth", () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));

function type(overrides: Partial<ActivityType> = {}): ActivityType {
  return {
    id: "at-1",
    slug: "mock-interview",
    name: "Mock Interview",
    description: "",
    category: "interview",
    allowed_creator_roles: ["manager", "trainer"],
    allowed_assignee_roles: ["trainer"],
    visible_to_student: true,
    default_duration_minutes: 30,
    form: null,
    requires_review: false,
    performance_weight: "1.00",
    risk_effect: "none",
    reminder_minutes_before: null,
    next_action: null,
    is_system: true,
    status: "active",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

function mockUseApi(rows: ActivityType[]) {
  useApi.mockImplementation((path: string) => {
    if (path === "/api/v1/activity-types/") {
      return { data: { results: rows }, error: null, isLoading: false, reload: vi.fn() };
    }
    return { data: { results: [] }, error: null, isLoading: false, reload: vi.fn() };
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ActivityTypesPage — progressive disclosure (Phase R7 Target 3)", () => {
  it("starts a new type's non-essential sections collapsed", () => {
    mockUseApi([]);
    render(<ActivityTypesPage />);
    fireEvent.click(screen.getAllByRole("button", { name: "New type" })[0]!);

    // The core fields stay unconditionally visible.
    expect(screen.getByRole("textbox", { name: "Name" })).toBeVisible();
    // Everything staged behind a section is present (so a screen reader /
    // in-page search still finds it) but not visible until opened.
    expect(screen.getByText("Who may create it")).not.toBeVisible();
    expect(screen.getByLabelText("Default duration (minutes)")).not.toBeVisible();
    expect(screen.getByLabelText("Performance weight")).not.toBeVisible();
  });

  it("opens a section by clicking its summary", () => {
    mockUseApi([]);
    render(<ActivityTypesPage />);
    fireEvent.click(screen.getAllByRole("button", { name: "New type" })[0]!);

    fireEvent.click(screen.getByText("Who can do this, and who sees it"));
    expect(screen.getByText("Who may create it")).toBeVisible();
  });

  it("starts every section open when editing an existing type", () => {
    mockUseApi([type()]);
    render(<ActivityTypesPage />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByText("Who may create it")).toBeVisible();
    expect(screen.getByLabelText("Default duration (minutes)")).toBeVisible();
    expect(screen.getByLabelText("Performance weight")).toBeVisible();
    // Editing also shows Status, only ever staged for an existing record.
    expect(screen.getByLabelText("Status")).toBeVisible();
  });

  it("forces a section open when the server returns an error for one of its fields, even for a new type", async () => {
    mockUseApi([]);
    vi.mocked(createActivityType).mockRejectedValue(
      new ApiError(400, "validation_error", "The submitted data is invalid.", "req-1", {
        default_duration_minutes: ["Ensure this value is greater than or equal to 0."],
      }),
    );
    render(<ActivityTypesPage />);
    fireEvent.click(screen.getAllByRole("button", { name: "New type" })[0]!);

    // Collapsed before submitting.
    expect(screen.getByLabelText("Default duration (minutes)")).not.toBeVisible();

    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), {
      target: { value: "Doubt session" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create type" }));

    expect(
      await screen.findByText("Ensure this value is greater than or equal to 0."),
    ).toBeVisible();
    expect(screen.getByLabelText("Default duration (minutes)")).toBeVisible();
  });
});
