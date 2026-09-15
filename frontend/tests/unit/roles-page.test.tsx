/**
 * Roles list: system roles carry the lock, custom roles can be removed with a
 * reason, and the removal is refused while people still hold the role.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RolesPage from "@/app/admin/roles/page";
import type { RoleSummary } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));
const deleteRole = vi.hoisted(() => vi.fn());
vi.mock("@/lib/roles", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/roles")>("@/lib/roles");
  return { ...actual, deleteRole };
});
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: "admin", capabilities: ["role.view", "role.manage"] },
    can: () => true,
  }),
}));
vi.mock("@/components/require-auth", () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
  usePathname: () => "/admin/roles",
}));

function role(overrides: Partial<RoleSummary>): RoleSummary {
  return {
    id: "r",
    slug: "manager",
    name: "Manager",
    description: "",
    kind: "manager",
    status: "active",
    is_system: true,
    is_locked: false,
    user_count: 3,
    permission_count: 52,
    updated_at: "2026-09-15T10:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RolesPage", () => {
  it("lists system and custom roles and removes a custom one with a reason", async () => {
    const reload = vi.fn();
    useApi.mockReturnValue({
      data: [
        role({}),
        role({
          id: "c",
          slug: "placement-coordinator",
          name: "Placement coordinator",
          is_system: false,
          user_count: 0,
          permission_count: 40,
        }),
      ],
      error: null,
      isLoading: false,
      reload,
    });
    deleteRole.mockResolvedValue(undefined);
    render(<RolesPage />);
    expect(screen.getByRole("link", { name: "Manager" })).toHaveAttribute(
      "href",
      "/admin/roles/manager",
    );
    expect(screen.getByText("System")).toBeInTheDocument();
    // Only the custom role offers Remove.
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    fireEvent.change(screen.getByLabelText("Why remove it?"), {
      target: { value: "Replaced" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Remove role" }));
    await waitFor(() =>
      expect(deleteRole).toHaveBeenCalledWith(
        "placement-coordinator",
        "Replaced",
      ),
    );
    expect(
      await screen.findByText(/removed\. It can be restored/),
    ).toBeInTheDocument();
    expect(reload).toHaveBeenCalled();
  });

  it("refuses removal while people hold the role", () => {
    useApi.mockReturnValue({
      data: [
        role({
          slug: "front-desk",
          name: "Front desk",
          is_system: false,
          user_count: 2,
        }),
      ],
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<RolesPage />);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(
      screen.getByText(/2 account\(s\) still hold this role/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Why remove it?")).not.toBeInTheDocument();
  });

  it("shows the error state with a retry", () => {
    const reload = vi.fn();
    useApi.mockReturnValue({
      data: null,
      error: { message: "Down", requestId: "r1" },
      isLoading: false,
      reload,
    });
    render(<RolesPage />);
    expect(screen.getByText("Could not load roles")).toBeInTheDocument();
  });
});
