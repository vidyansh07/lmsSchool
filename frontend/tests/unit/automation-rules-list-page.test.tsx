/**
 * Automation rules list (`/admin/automation`): loading, empty, error, denied
 * and success states, plus creating a new rule.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AutomationRulesPage from "@/app/admin/automation/page";
import { ApiError } from "@/lib/api";
import type { AutomationRule, Paginated } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

const createAutomationRule = vi.hoisted(() => vi.fn());
vi.mock("@/lib/automation", async () => {
  const actual = await vi.importActual<typeof import("@/lib/automation")>("@/lib/automation");
  return { ...actual, createAutomationRule };
});

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

const auth = vi.hoisted(() => ({
  capabilities: ["automation.manage"] as string[],
}));
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: "admin", capabilities: auth.capabilities },
    isLoading: false,
    can: (capability: string) => auth.capabilities.includes(capability),
  }),
}));

function rule(overrides: Partial<AutomationRule> = {}): AutomationRule {
  return {
    id: "rule-1",
    name: "Communication practice after a weak mock",
    description: "",
    trigger: "ACTIVITY_COMPLETED",
    conditions: [],
    actions: [],
    status: "active",
    version: 2,
    branch: null,
    is_system: true,
    created_by: null,
    updated_by: null,
    created_by_name: "Rajat Goyal",
    updated_by_name: "Rajat Goyal",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-10T10:00:00Z",
    ...overrides,
  };
}

function page(results: AutomationRule[]): Paginated<AutomationRule> {
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

/** The list and the status cards are two calls; the cards are counted on the
 *  server, so the summary is its own fixture rather than the page's length. */
function mockApi(
  list: Paginated<AutomationRule> | null,
  counts: { total: number; active: number; draft: number; paused: number } | null = {
    total: 2,
    active: 1,
    draft: 1,
    paused: 0,
  },
  extra: { error?: { message: string; requestId?: string } | null; isLoading?: boolean } = {},
) {
  useApi.mockImplementation((path: string) => {
    if (path.includes("summary")) {
      return { data: counts, error: null, isLoading: false, reload: vi.fn() };
    }
    return {
      data: list,
      error: extra.error ?? null,
      isLoading: extra.isLoading ?? false,
      reload: vi.fn(),
    };
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.capabilities = ["automation.manage"];
});

describe("AutomationRulesPage", () => {
  it("shows a loading state", () => {
    mockApi(null, null, { isLoading: true });
    render(<AutomationRulesPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state with a New rule action", () => {
    mockApi(page([]));
    render(<AutomationRulesPage />);
    expect(screen.getByText("No automations yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /create automation/i }).length).toBeGreaterThan(0);
  });

  it("shows an error state with retry", () => {
    const reload = vi.fn();
    useApi.mockReturnValue({
      data: null,
      error: new ApiError(500, "server_error", "Could not load automation rules.", "req-1"),
      isLoading: false,
      reload,
    });
    render(<AutomationRulesPage />);
    expect(screen.getAllByText(/could not load automation rules/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(reload).toHaveBeenCalled();
  });

  it("hides the page from a caller without automation.manage", () => {
    auth.capabilities = [];
    useApi.mockReturnValue({ data: null, error: null, isLoading: true, reload: vi.fn() });
    render(<AutomationRulesPage />);
    expect(screen.getByText(/do not have access/i)).toBeInTheDocument();
    expect(screen.queryByText("Automation")).not.toBeInTheDocument();
  });

  it("lists rules with their trigger, status and version", () => {
    const data = page([
      rule(),
      rule({
        id: "rule-2",
        name: "Attendance counselling",
        trigger: "ATTENDANCE_THRESHOLD",
        status: "draft",
        version: 1,
        is_system: false,
      }),
    ]);
    mockApi(data);
    render(<AutomationRulesPage />);
    expect(
      screen.getByRole("link", { name: "Communication practice after a weak mock" }),
    ).toHaveAttribute("href", "/admin/automation/rule-1");
    // The reference product's own columns.
    expect(screen.getByRole("columnheader", { name: "Automation Name" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Module" })).toBeInTheDocument();
    expect(screen.getAllByText("Rajat Goyal").length).toBeGreaterThan(0);
    expect(screen.getByText("Activity completed")).toBeInTheDocument();
    expect(screen.getByText("Total Automation — 2")).toBeInTheDocument();
    expect(screen.getByText("Attendance crossed a threshold")).toBeInTheDocument();
    // "Active" and "Draft" appear twice now: once as a status card, once as
    // a row's badge.
    expect(screen.getAllByText("Active")).toHaveLength(2);
    expect(screen.getAllByText("Draft")).toHaveLength(2);
    expect(screen.getByText(/v2/)).toBeInTheDocument();
    expect(screen.getByText(/seeded/)).toBeInTheDocument();
  });

  it("asks the server for one status when a card is pressed, and lets go again", () => {
    const paths: string[] = [];
    useApi.mockImplementation((path: string) => {
      paths.push(path);
      if (path.includes("summary")) {
        return {
          data: { total: 3, active: 1, draft: 1, paused: 1 },
          error: null,
          isLoading: false,
          reload: vi.fn(),
        };
      }
      return { data: page([rule()]), error: null, isLoading: false, reload: vi.fn() };
    });
    render(<AutomationRulesPage />);

    fireEvent.click(screen.getByRole("button", { name: "Paused: 1" }));
    expect(paths.some((path) => path.includes("status=paused"))).toBe(true);

    // Pressing it again clears the filter rather than leaving no way back.
    fireEvent.click(screen.getByRole("button", { name: "Paused: 1" }));
    expect(paths.at(-1)).not.toContain("status=");
  });

  it("walks the four steps and creates the rule as a draft", async () => {
    mockApi(page([]));
    createAutomationRule.mockResolvedValue(rule({ id: "rule-new", status: "draft" }));
    render(<AutomationRulesPage />);

    fireEvent.click(screen.getAllByRole("button", { name: /create automation/i })[0]!);

    // Category narrows nineteen triggers to the handful that are about this
    // kind of record.
    fireEvent.click(screen.getByRole("button", { name: /^Student/ }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: /^Project overdue/ }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    // Conditions may be skipped; the review step says what that means.
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(/runs for every single student/)).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: /Automation name/ }), {
      target: { value: "Project overdue nudge" },
    });
    // The page's own button says the same thing, so this is the dialog's.
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Create Automation" }),
    );

    await waitFor(() =>
      expect(createAutomationRule).toHaveBeenCalledWith({
        name: "Project overdue nudge",
        trigger: "PROJECT_OVERDUE",
      }),
    );
    expect(push).toHaveBeenCalledWith("/admin/automation/rule-new");
  });

  it("will not go on from a step that has not been answered", () => {
    mockApi(page([]));
    render(<AutomationRulesPage />);
    fireEvent.click(screen.getAllByRole("button", { name: /create automation/i })[0]!);

    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /^Fee/ }));
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });
});
