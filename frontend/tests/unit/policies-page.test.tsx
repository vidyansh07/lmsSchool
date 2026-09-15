/**
 * The Policy Builder: category list left, keys right, an edit dialog that
 * needs a fresh step-up and a typed confirmation for a critical key, a reset
 * dialog, and a history dialog — plus the denied state a caller without
 * `policy.view` gets from the real page.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PoliciesPage, { PoliciesScreen } from "@/app/admin/policies/page";
import type { Paginated, PolicyEntry, PolicyVersion } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

const updatePolicy = vi.hoisted(() => vi.fn());
const resetPolicy = vi.hoisted(() => vi.fn());
const getPolicyHistory = vi.hoisted(() => vi.fn());
vi.mock("@/lib/policies", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/policies")>("@/lib/policies");
  return { ...actual, updatePolicy, resetPolicy, getPolicyHistory };
});

const stepUpWithPassword = vi.hoisted(() => vi.fn());
vi.mock("@/lib/roles", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/roles")>("@/lib/roles");
  return { ...actual, stepUpWithPassword };
});

const auth = vi.hoisted(() => ({
  capabilities: ["policy.view", "policy.manage"] as string[],
}));
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: "admin", capabilities: auth.capabilities },
    isLoading: false,
    can: (capability: string) => auth.capabilities.includes(capability),
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/admin/policies",
}));

function entry(overrides: Partial<PolicyEntry>): PolicyEntry {
  return {
    category: "authentication",
    key: "lockout_after",
    value: 10,
    default: 10,
    is_default: true,
    scope: "global",
    branch: null,
    version: 0,
    critical: false,
    description: "Failed logins within 15 minutes before the account locks.",
    updated_at: null,
    updated_by_name: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.capabilities = ["policy.view", "policy.manage"];
});

describe("PoliciesScreen", () => {
  it("shows a loading skeleton", () => {
    useApi.mockReturnValue({
      data: null,
      error: null,
      isLoading: true,
      reload: vi.fn(),
    });
    render(<PoliciesScreen />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows the error state with a retry", () => {
    useApi.mockReturnValue({
      data: null,
      error: { message: "Down", requestId: "r1" },
      isLoading: false,
      reload: vi.fn(),
    });
    render(<PoliciesScreen />);
    expect(screen.getByText("Could not load policies")).toBeInTheDocument();
  });

  it("shows the empty state when the schema is unseeded", () => {
    useApi.mockReturnValue({
      data: [],
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<PoliciesScreen />);
    expect(screen.getByText("No policies")).toBeInTheDocument();
  });

  it("groups keys by category and switches between them", () => {
    useApi.mockReturnValue({
      data: [
        entry({}),
        entry({
          category: "session",
          key: "idle_minutes",
          value: 30,
          default: 0,
          is_default: false,
          description: "Idle timeout in minutes.",
          updated_by_name: "Amy Admin",
          updated_at: "2026-09-15T10:00:00Z",
        }),
      ],
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<PoliciesScreen />);
    // Authentication is first in the fixed category order, so it opens by default.
    expect(screen.getByText(/Failed logins within/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Idle timeout in minutes/),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Session/ }));
    expect(screen.getByText(/Idle timeout in minutes/)).toBeInTheDocument();
    expect(screen.getByText(/Changed by Amy Admin/)).toBeInTheDocument();
    expect(screen.getByText("Custom")).toBeInTheDocument();
  });

  it("edits a non-critical value with a reason, no step-up needed", async () => {
    const reload = vi.fn();
    useApi.mockReturnValue({
      data: [entry({})],
      error: null,
      isLoading: false,
      reload,
    });
    updatePolicy.mockResolvedValue(entry({ value: 15, is_default: false }));

    render(<PoliciesScreen />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("New value"), {
      target: { value: "15" },
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Tighten lockouts" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(updatePolicy).toHaveBeenCalledWith(
        "authentication",
        "lockout_after",
        { value: 15, reason: "Tighten lockouts", confirm: undefined },
      ),
    );
    expect(
      await screen.findByText('"authentication.lockout_after" updated.'),
    ).toBeInTheDocument();
    expect(reload).toHaveBeenCalled();
  });

  it("requires a fresh step-up and the typed key for a critical value", async () => {
    useApi.mockReturnValue({
      data: [
        entry({
          category: "password",
          key: "min_length",
          value: 10,
          default: 10,
          critical: true,
          description: "Shortest password Django's validators accept.",
        }),
      ],
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    updatePolicy.mockRejectedValueOnce(
      Object.assign(new Error("Confirm it is you before doing this."), {
        status: 403,
        code: "step_up_required",
        details: null,
      }),
    );
    updatePolicy.mockResolvedValueOnce(
      entry({ category: "password", key: "min_length", value: 12 }),
    );
    stepUpWithPassword.mockResolvedValue(undefined);

    render(<PoliciesScreen />);
    fireEvent.click(screen.getByRole("button", { name: /^Password/ }));
    expect(screen.getByText("Critical")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.change(screen.getByLabelText("New value"), {
      target: { value: "12" },
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Raise the floor" },
    });
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Type "min_length" to confirm'), {
      target: { value: "min_length" },
    });
    expect(save).not.toBeDisabled();
    fireEvent.click(save);

    expect(await screen.findByText("Confirm it is you")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(stepUpWithPassword).toHaveBeenCalledWith("secret"),
    );
    await waitFor(() => expect(updatePolicy).toHaveBeenCalledTimes(2));
    expect(updatePolicy).toHaveBeenLastCalledWith("password", "min_length", {
      value: 12,
      reason: "Raise the floor",
      confirm: "min_length",
    });
  });

  it("resets a custom value to its default", async () => {
    const reload = vi.fn();
    useApi.mockReturnValue({
      data: [
        entry({
          category: "session",
          key: "idle_minutes",
          value: 30,
          default: 0,
          is_default: false,
        }),
      ],
      error: null,
      isLoading: false,
      reload,
    });
    resetPolicy.mockResolvedValue(
      entry({ category: "session", key: "idle_minutes", value: 0 }),
    );

    render(<PoliciesScreen />);
    fireEvent.click(screen.getByRole("button", { name: /^Session/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.getByText("Reset session.idle_minutes?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset to default" }));

    await waitFor(() =>
      expect(resetPolicy).toHaveBeenCalledWith("session", "idle_minutes"),
    );
    expect(
      await screen.findByText('"session.idle_minutes" reset to its default.'),
    ).toBeInTheDocument();
    expect(reload).toHaveBeenCalled();
  });

  it("does not offer edit or reset without policy.manage", () => {
    auth.capabilities = ["policy.view"];
    useApi.mockReturnValue({
      data: [
        entry({
          category: "session",
          key: "idle_minutes",
          is_default: false,
        }),
      ],
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<PoliciesScreen />);
    fireEvent.click(screen.getByRole("button", { name: /^Session/ }));
    expect(
      screen.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reset" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "History" })).toBeInTheDocument();
  });

  it("shows a key's history, newest first", async () => {
    useApi.mockReturnValue({
      data: [entry({})],
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    const history: Paginated<PolicyVersion> = {
      count: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
      next: null,
      previous: null,
      results: [
        {
          id: "v1",
          version: 2,
          value: 15,
          changed_by_name: "Amy Admin",
          reason: "Tighten lockouts",
          created_at: "2026-09-15T10:00:00Z",
        },
      ],
    };
    getPolicyHistory.mockResolvedValue(history);

    render(<PoliciesScreen />);
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    expect(
      await screen.findByText("History: authentication.lockout_after"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Amy Admin")).toBeInTheDocument();
    expect(screen.getByText("Tighten lockouts")).toBeInTheDocument();
    expect(getPolicyHistory).toHaveBeenCalledWith(
      "authentication",
      "lockout_after",
      { page: 1 },
    );
  });
});

describe("PoliciesPage", () => {
  it("hides the page from a caller without policy.view", () => {
    auth.capabilities = [];
    render(<PoliciesPage />);
    expect(screen.getByText(/do not have access/i)).toBeInTheDocument();
    expect(screen.queryByText("Policies")).not.toBeInTheDocument();
  });
});
