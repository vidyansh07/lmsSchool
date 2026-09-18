/**
 * Activity types: the list renders the seeded catalog, and creating a new
 * type posts the built payload and reloads the list.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ActivityTypesPage from "@/app/admin/activity-types/page";
import { ApiError } from "@/lib/api";
import type { ActivityType } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

const createActivityType = vi.hoisted(() => vi.fn());
vi.mock("@/lib/work", async () => {
  const actual = await vi.importActual<typeof import("@/lib/work")>("@/lib/work");
  return { ...actual, createActivityType };
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
    form: { id: "form-1", slug: "mock-interview" },
    requires_review: false,
    performance_weight: "1.00",
    risk_effect: "score_below_threshold",
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
  const reload = vi.fn();
  useApi.mockImplementation((path: string) => {
    if (path === "/api/v1/activity-types/") {
      return { data: { results: rows }, error: null, isLoading: false, reload };
    }
    return { data: { results: [] }, error: null, isLoading: false, reload: vi.fn() };
  });
  return reload;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ActivityTypesPage", () => {
  it("lists the catalog", () => {
    mockUseApi([
      type(),
      type({ slug: "career-guidance", name: "Career Guidance", category: "counselling" }),
    ]);
    render(<ActivityTypesPage />);
    expect(screen.getByText("Mock Interview")).toBeInTheDocument();
    expect(screen.getByText("Career Guidance")).toBeInTheDocument();
    expect(screen.getByText("Counselling")).toBeInTheDocument();
    expect(screen.getAllByText("Active")).toHaveLength(2);
  });

  it("shows the loading state", () => {
    useApi.mockReturnValue({ data: null, error: null, isLoading: true, reload: vi.fn() });
    render(<ActivityTypesPage />);
    expect(screen.getByText(/Loading activity types/)).toBeInTheDocument();
  });

  it("shows the error state", () => {
    useApi.mockReturnValue({
      data: null,
      error: { message: "Down", requestId: "req-1" },
      isLoading: false,
      reload: vi.fn(),
    });
    render(<ActivityTypesPage />);
    expect(screen.getByText("Could not load activity types")).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    mockUseApi([]);
    render(<ActivityTypesPage />);
    expect(screen.getByText("No activity types yet")).toBeInTheDocument();
  });

  it("creates a new type and reloads the list", async () => {
    const reload = mockUseApi([]);
    createActivityType.mockResolvedValue(type({ slug: "doubt-session", name: "Doubt Session" }));
    render(<ActivityTypesPage />);

    fireEvent.click(screen.getAllByRole("button", { name: "New type" })[0]!);
    // Not `getByLabelText`: this field is required, and `Field` renders the
    // `*` as an `aria-hidden` sibling span, which testing-library's label
    // matcher includes in the label's plain text ("Name*") while the real
    // accessible-name algorithm `getByRole` uses correctly excludes it.
    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), {
      target: { value: "Doubt Session" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create type" }));

    await waitFor(() =>
      expect(createActivityType).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Doubt Session", slug: "doubt-session" }),
      ),
    );
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });
});

describe("ActivityTypeDialog — Phase R7 Target 3", () => {
  it("uses the app-wide sm:grid-cols-2 convention for the Duration/Reminder and Weight/Risk pairs, not a bare grid-cols-2", () => {
    mockUseApi([]);
    const { container } = render(<ActivityTypesPage />);
    fireEvent.click(screen.getAllByRole("button", { name: "New type" })[0]!);

    // Both pairs collapse to one column below `sm:`, same as every other
    // multi-column field grid in the app (e.g. `create-student-dialog.tsx`).
    expect(container.querySelectorAll(".grid.gap-4.sm\\:grid-cols-2").length).toBe(2);
    // No leftover bare `grid-cols-2` (no `sm:` prefix) anywhere in the dialog.
    const bareTwoColumnGrids = Array.from(container.querySelectorAll<HTMLElement>("div")).filter(
      (el) => el.classList.contains("grid-cols-2") && !el.classList.contains("sm:grid-cols-2"),
    );
    expect(bareTwoColumnGrids).toHaveLength(0);
  });

  it("groups the two role-checkbox groups under one shared heading — the one real grouping the form implies", () => {
    mockUseApi([]);
    render(<ActivityTypesPage />);
    fireEvent.click(screen.getAllByRole("button", { name: "New type" })[0]!);

    const rolesGroup = screen.getByText("Roles").closest("fieldset");
    expect(rolesGroup).not.toBeNull();
    expect(rolesGroup).toContainElement(screen.getByRole("group", { name: "Who may create it" }));
    expect(rolesGroup).toContainElement(
      screen.getByRole("group", { name: "Who may be assigned it" }),
    );
  });

  it("wires a role-checkbox group's error through aria-describedby, not a bare disconnected <p>", async () => {
    mockUseApi([]);
    createActivityType.mockRejectedValue(
      new ApiError(400, "validation_error", "The submitted data is invalid.", "req-1", {
        allowed_creator_roles: ["Choose at least one role."],
      }),
    );
    render(<ActivityTypesPage />);
    fireEvent.click(screen.getAllByRole("button", { name: "New type" })[0]!);

    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), {
      target: { value: "Doubt Session" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create type" }));

    const message = await screen.findByText("Choose at least one role.");
    const group = screen.getByRole("group", { name: "Who may create it" });
    expect(group).toHaveAttribute("aria-describedby", message.id);
  });
});
