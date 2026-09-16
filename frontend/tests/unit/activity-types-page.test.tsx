/**
 * Activity types: the list renders the seeded catalog, and creating a new
 * type posts the built payload and reloads the list.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ActivityTypesPage from "@/app/admin/activity-types/page";
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
