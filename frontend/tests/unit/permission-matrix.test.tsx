/**
 * The matrix names each cell's state in text, not only in colour. A
 * superadmin holding `permission.lock` can lock or unlock a granted cell
 * directly, with a fresh step-up first (ADR-03).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PermissionMatrix } from "@/components/roles/permission-matrix";
import type { RoleMatrix } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

const lockPermission = vi.hoisted(() => vi.fn());
const unlockPermission = vi.hoisted(() => vi.fn());
const stepUpWithPassword = vi.hoisted(() => vi.fn());
vi.mock("@/lib/roles", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/roles")>("@/lib/roles");
  return { ...actual, lockPermission, unlockPermission, stepUpWithPassword };
});

const auth = vi.hoisted(() => ({
  capabilities: ["role.view"] as string[],
}));
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: "admin", capabilities: auth.capabilities },
    can: () => true,
  }),
}));

const matrix: RoleMatrix = {
  roles: [
    {
      id: "s",
      slug: "superadmin",
      name: "Superadmin",
      description: "",
      kind: "superadmin",
      status: "active",
      is_system: true,
      is_locked: true,
      user_count: 1,
      permission_count: 74,
      updated_at: "",
    },
    {
      id: "a",
      slug: "admin",
      name: "Administrator",
      description: "",
      kind: "admin",
      status: "active",
      is_system: true,
      is_locked: false,
      user_count: 2,
      permission_count: 60,
      updated_at: "",
    },
  ],
  permissions: [
    {
      code: "record.purge",
      resource: "record",
      action: "purge",
      category: "system",
      description: "Destroy a record",
      is_lockable: true,
      is_active: true,
    },
    {
      code: "student.view_any",
      resource: "student",
      action: "view_any",
      category: "people",
      description: "View any student",
      is_lockable: false,
      is_active: true,
    },
  ],
  cells: {
    superadmin: { "record.purge": "system", "student.view_any": "system" },
    admin: { "record.purge": "denied", "student.view_any": "inherited" },
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  auth.capabilities = ["role.view"];
});

describe("PermissionMatrix", () => {
  it("renders the states as text and filters by category", () => {
    useApi.mockReturnValue({
      data: matrix,
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<PermissionMatrix />);
    expect(screen.getByText("Destroy a record")).toBeInTheDocument();
    expect(screen.getAllByText("Not granted").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Inherited").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Category"), {
      target: { value: "people" },
    });
    expect(screen.queryByText("Destroy a record")).not.toBeInTheDocument();
    expect(screen.getByText("View any student")).toBeInTheDocument();
  });

  it("does not offer lock controls without permission.lock", () => {
    useApi.mockReturnValue({
      data: matrix,
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<PermissionMatrix />);
    expect(screen.queryByTitle("Lock this grant")).not.toBeInTheDocument();
    expect(screen.queryByTitle("Unlock this grant")).not.toBeInTheDocument();
  });

  it("locks a granted cell after a fresh step-up", async () => {
    auth.capabilities = ["role.view", "permission.lock"];
    const reload = vi.fn();
    useApi.mockReturnValue({
      data: matrix,
      error: null,
      isLoading: false,
      reload,
    });
    lockPermission.mockRejectedValueOnce(
      Object.assign(new Error("Confirm it is you before doing this."), {
        status: 403,
        code: "step_up_required",
        details: null,
      }),
    );
    lockPermission.mockResolvedValueOnce(undefined);
    stepUpWithPassword.mockResolvedValue(undefined);

    render(<PermissionMatrix />);
    fireEvent.click(screen.getByTitle("Lock this grant"));
    expect(await screen.findByText("Confirm it is you")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(stepUpWithPassword).toHaveBeenCalledWith("secret"),
    );
    await waitFor(() => expect(lockPermission).toHaveBeenCalledTimes(2));
    expect(lockPermission).toHaveBeenLastCalledWith(
      "admin",
      "student.view_any",
    );
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });
});
