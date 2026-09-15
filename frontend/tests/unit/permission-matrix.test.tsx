/** The matrix names each cell's state in text, not only in colour. */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PermissionMatrix } from "@/components/roles/permission-matrix";
import type { RoleMatrix } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

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
});
