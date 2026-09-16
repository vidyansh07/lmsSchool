/**
 * The activities work list: every data state, that a filter change
 * re-queries `listActivities` with the right query parameters, and that the
 * page is denied to a viewer without `activity.view_any`.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ActivitiesPage from "@/app/activities/page";
import { ApiError } from "@/lib/api";
import type { Activity, Paginated } from "@/types/api";

const listActivities = vi.hoisted(() => vi.fn());
const listActivityTypes = vi.hoisted(() => vi.fn());
vi.mock("@/lib/work", async () => {
  const actual = await vi.importActual<typeof import("@/lib/work")>("@/lib/work");
  return { ...actual, listActivities, listActivityTypes };
});
// The drawer has its own dedicated tests (`activity-drawer.test.tsx`); here
// it would only add unrelated fetches to mock.
vi.mock("@/components/work/activity-drawer", () => ({
  ActivityDrawer: () => null,
}));

const useAuth = vi.hoisted(() => vi.fn());
vi.mock("@/components/auth-provider", () => ({ useAuth }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

function row(overrides: Partial<Activity> = {}): Activity {
  return {
    id: "a1",
    title: "Mock interview with Asha",
    status: "assigned",
    priority: "normal",
    planned_at: "2026-09-18T10:00:00Z",
    due_at: "2026-09-20T10:00:00Z",
    completed_at: null,
    created_at: "2026-09-16T09:00:00Z",
    student: { id: "s1", name: "Asha Rao", student_id: "STU-001" },
    type: { id: "t1", slug: "mock-interview", name: "Mock Interview", category: "interview" },
    batch: null,
    assigned_to: { id: "u1", name: "Trainer One" },
    created_by: { id: "u2", name: "Manager One" },
    counts: { history: 0 },
    ...overrides,
  };
}

function paginated(results: Activity[]): Paginated<Activity> {
  return {
    count: results.length,
    page: 1,
    page_size: 25,
    total_pages: 1,
    next: null,
    previous: null,
    results,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listActivityTypes.mockResolvedValue({ results: [] });
  useAuth.mockReturnValue({
    user: { id: "u1", role: "manager", capabilities: ["activity.view_any"] },
    isLoading: false,
    can: (capability: string) => capability === "activity.view_any",
  });
});

describe("ActivitiesPage", () => {
  it("shows a loading state while the list is in flight", () => {
    listActivities.mockReturnValue(new Promise(() => {}));
    render(<ActivitiesPage />);
    expect(screen.getByText(/Loading activities/)).toBeInTheDocument();
  });

  it("shows an empty state when nothing matches the filters", async () => {
    listActivities.mockResolvedValue(paginated([]));
    render(<ActivitiesPage />);
    expect(
      await screen.findByText("No activities match these filters"),
    ).toBeInTheDocument();
  });

  it("shows an error state with a retry that re-fetches", async () => {
    listActivities.mockRejectedValueOnce(new ApiError(500, "error", "Down", "req-1"));
    render(<ActivitiesPage />);
    expect(await screen.findByText("Could not load activities")).toBeInTheDocument();

    listActivities.mockResolvedValueOnce(paginated([]));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(listActivities).toHaveBeenCalledTimes(2));
  });

  it("renders rows on success", async () => {
    listActivities.mockResolvedValue(paginated([row()]));
    render(<ActivitiesPage />);
    expect(await screen.findByText("Mock interview with Asha")).toBeInTheDocument();
    expect(screen.getByText("Asha Rao")).toBeInTheDocument();
    expect(screen.getByText("Trainer One")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("Assigned")).toBeInTheDocument();
  });

  it("shows the denied state for a viewer without activity.view_any or a trainer role", async () => {
    useAuth.mockReturnValue({
      user: { id: "u2", role: "student", capabilities: [] },
      isLoading: false,
      can: () => false,
    });
    render(<ActivitiesPage />);
    expect(
      await screen.findByText("You do not have access to this page"),
    ).toBeInTheDocument();
    expect(listActivities).not.toHaveBeenCalled();
  });

  it("lets a trainer in even without activity.view_any, since their reach is resolved per-record on the backend", async () => {
    listActivities.mockResolvedValue(paginated([row()]));
    useAuth.mockReturnValue({
      user: { id: "u3", role: "trainer", capabilities: [] },
      isLoading: false,
      can: () => false,
    });
    render(<ActivitiesPage />);
    expect(await screen.findByText("Mock interview with Asha")).toBeInTheDocument();
  });

  it("re-queries with the chosen filters", async () => {
    listActivities.mockResolvedValue(paginated([]));
    render(<ActivitiesPage />);
    await waitFor(() =>
      expect(listActivities).toHaveBeenLastCalledWith({
        status: undefined,
        type: undefined,
        assigned_to: undefined,
        mine: undefined,
        overdue: undefined,
        page: 1,
      }),
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "Overdue" }));
    await waitFor(() =>
      expect(listActivities).toHaveBeenLastCalledWith(
        expect.objectContaining({ overdue: 1, page: 1 }),
      ),
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "Mine" }));
    await waitFor(() =>
      expect(listActivities).toHaveBeenLastCalledWith(
        expect.objectContaining({ overdue: 1, mine: 1, page: 1 }),
      ),
    );
  });
});
