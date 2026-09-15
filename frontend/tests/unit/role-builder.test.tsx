/**
 * The Role Builder: starts from the kind's system set, lets an administrator
 * switch permissions and pick a scope no wider than the kind allows, shows
 * the diff on review, and writes only on Create.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RoleBuilder } from "@/components/roles/role-builder";
import { ApiError } from "@/lib/api";
import type { PermissionDef, Role, RoleSummary } from "@/types/api";

const listPermissions = vi.hoisted(() => vi.fn());
const listRoles = vi.hoisted(() => vi.fn());
const getRole = vi.hoisted(() => vi.fn());
const createRole = vi.hoisted(() => vi.fn());
const updateRole = vi.hoisted(() => vi.fn());
vi.mock("@/lib/roles", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/roles")>("@/lib/roles");
  return {
    ...actual,
    listPermissions,
    listRoles,
    getRole,
    createRole,
    updateRole,
  };
});
const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(""),
  usePathname: () => "/admin/roles/new",
}));
const auth = vi.hoisted(() => ({
  capabilities: ["role.view", "role.manage", "permission.assign"],
}));
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: "admin", capabilities: auth.capabilities },
    can: () => true,
  }),
}));

const defs: PermissionDef[] = [
  {
    code: "student.view_any",
    resource: "student",
    action: "view_any",
    category: "people",
    description: "View any student",
    is_lockable: false,
    is_active: true,
  },
  {
    code: "fee.manage_any",
    resource: "fee",
    action: "manage_any",
    category: "people",
    description: "Manage fees",
    is_lockable: true,
    is_active: true,
  },
  {
    code: "dsr.review",
    resource: "dsr",
    action: "review",
    category: "operations",
    description: "Review daily reports",
    is_lockable: false,
    is_active: true,
  },
];
const managerSummary: RoleSummary = {
  id: "m",
  slug: "manager",
  name: "Manager",
  description: "",
  kind: "manager",
  status: "active",
  is_system: true,
  is_locked: false,
  user_count: 3,
  permission_count: 3,
  updated_at: "",
};
const managerRole: Role = {
  ...managerSummary,
  permissions: defs.map((d) => ({ code: d.code, scope: "", is_locked: false })),
  updated_by_name: null,
  created_at: "",
};

beforeEach(() => {
  vi.clearAllMocks();
  auth.capabilities = ["role.view", "role.manage", "permission.assign"];
  listPermissions.mockResolvedValue(defs);
  listRoles.mockResolvedValue([managerSummary]);
  getRole.mockResolvedValue(managerRole);
});

describe("RoleBuilder", () => {
  it("creates a narrower role: name, switch off, scope, review diff, create", async () => {
    createRole.mockResolvedValue({
      ...managerRole,
      slug: "placement-coordinator",
    });
    render(<RoleBuilder />);
    const name = await screen.findByLabelText("Name");
    fireEvent.change(name, { target: { value: "Placement coordinator" } });
    expect(screen.getByLabelText("Slug")).toHaveValue("placement-coordinator");
    fireEvent.click(screen.getByRole("button", { name: "Permissions" }));

    // Starts from the manager set (three on); switch fees off.
    const fees = await screen.findByRole("switch", { name: "Manage fees" });
    expect(fees).toHaveAttribute("aria-checked", "true");
    fireEvent.click(fees);
    // A manager-kind role offers branch/assigned/own, never "every centre".
    const scope = screen.getByLabelText(
      "Scope for student.view_any",
    ) as HTMLSelectElement;
    expect([...scope.options].map((o) => o.value)).toEqual([
      "",
      "branch",
      "assigned",
      "own",
    ]);
    fireEvent.change(scope, { target: { value: "assigned" } });

    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(await screen.findByText("0 added")).toBeInTheDocument();
    expect(screen.getByText("1 removed")).toBeInTheDocument();
    expect(screen.getByText(/fee\.manage_any/)).toBeInTheDocument();
    expect(createRole).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Create role" }));
    await waitFor(() =>
      expect(createRole).toHaveBeenCalledWith({
        slug: "placement-coordinator",
        name: "Placement coordinator",
        kind: "manager",
        description: "",
        permissions: [
          { code: "student.view_any", scope: "assigned" },
          { code: "dsr.review", scope: "" },
        ],
      }),
    );
    expect(push).toHaveBeenCalledWith(
      "/admin/roles?created=placement-coordinator",
    );
  });

  it("edits a system role: name locked, description editable, permissions sent", async () => {
    updateRole.mockResolvedValue(managerRole);
    render(<RoleBuilder slug="manager" />);
    const name = await screen.findByLabelText("Name");
    expect(name).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Runs a centre." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Permissions" }));
    await screen.findByRole("switch", { name: "Manage fees" });
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(await screen.findByText(/3 hold this role now/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save role" }));
    await waitFor(() =>
      expect(updateRole).toHaveBeenCalledWith("manager", {
        description: "Runs a centre.",
        permissions: defs.map((d) => ({ code: d.code, scope: "" })),
      }),
    );
  });

  it("shows permissions read-only without permission.assign", async () => {
    auth.capabilities = ["role.view", "role.manage"];
    render(<RoleBuilder />);
    fireEvent.change(await screen.findByLabelText("Name"), {
      target: { value: "X" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Permissions" }));
    const fees = await screen.findByRole("switch", { name: "Manage fees" });
    expect(fees).toBeDisabled();
    expect(
      screen.getByText(/assigning permissions needs its own right/),
    ).toBeInTheDocument();
  });

  it("puts a server-side refusal on screen", async () => {
    createRole.mockRejectedValue(
      new ApiError(
        403,
        "outside_authority",
        "You cannot grant what you do not hold: audit.view.",
        "r1",
        null,
      ),
    );
    render(<RoleBuilder />);
    fireEvent.change(await screen.findByLabelText("Name"), {
      target: { value: "Wide" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Permissions" }));
    await screen.findByRole("switch", { name: "Manage fees" });
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    fireEvent.click(await screen.findByRole("button", { name: "Create role" }));
    expect(
      await screen.findByText(/You cannot grant what you do not hold/),
    ).toBeInTheDocument();
  });
});
