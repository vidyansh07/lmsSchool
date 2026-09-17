/**
 * Automation rules list (`/admin/automation`): loading, empty, error, denied
 * and success states, plus creating a new rule.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

beforeEach(() => {
  vi.clearAllMocks();
  auth.capabilities = ["automation.manage"];
});

describe("AutomationRulesPage", () => {
  it("shows a loading state", () => {
    useApi.mockReturnValue({ data: null, error: null, isLoading: true, reload: vi.fn() });
    render(<AutomationRulesPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state with a New rule action", () => {
    useApi.mockReturnValue({ data: page([]), error: null, isLoading: false, reload: vi.fn() });
    render(<AutomationRulesPage />);
    expect(screen.getByText("No automation rules yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /new rule/i }).length).toBeGreaterThan(0);
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
    useApi.mockReturnValue({ data, error: null, isLoading: false, reload: vi.fn() });
    render(<AutomationRulesPage />);
    expect(
      screen.getByRole("link", { name: "Communication practice after a weak mock" }),
    ).toHaveAttribute("href", "/admin/automation/rule-1");
    expect(screen.getByText("Activity completed")).toBeInTheDocument();
    expect(screen.getByText("Attendance crossed a threshold")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("Seeded")).toBeInTheDocument();
  });

  it("creates a new rule and navigates to its detail page", async () => {
    useApi.mockReturnValue({ data: page([]), error: null, isLoading: false, reload: vi.fn() });
    createAutomationRule.mockResolvedValue(rule({ id: "rule-new", status: "draft" }));
    render(<AutomationRulesPage />);

    const [newRuleButton] = screen.getAllByRole("button", { name: /new rule/i });
    fireEvent.click(newRuleButton!);
    fireEvent.change(screen.getByLabelText("Name", { exact: false }), {
      target: { value: "Project overdue nudge" },
    });
    fireEvent.change(screen.getByLabelText("Trigger", { exact: false }), {
      target: { value: "PROJECT_OVERDUE" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create rule/i }));

    await waitFor(() =>
      expect(createAutomationRule).toHaveBeenCalledWith({
        name: "Project overdue nudge",
        trigger: "PROJECT_OVERDUE",
      }),
    );
    expect(push).toHaveBeenCalledWith("/admin/automation/rule-new");
  });
});
