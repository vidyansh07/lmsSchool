/**
 * Forms list (`/admin/forms`): loading, empty, error, denied and success
 * states, plus creating a new definition.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FormsPage from "@/app/admin/forms/page";
import { ApiError } from "@/lib/api";
import type { FormDefinitionListResponse } from "@/lib/forms";
import type { FormDefinitionSummary } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

const createFormDefinition = vi.hoisted(() => vi.fn());
vi.mock("@/lib/forms", async () => {
  const actual = await vi.importActual<typeof import("@/lib/forms")>("@/lib/forms");
  return { ...actual, createFormDefinition };
});

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const auth = vi.hoisted(() => ({
  capabilities: ["form.view", "form.manage"] as string[],
}));
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: "admin", capabilities: auth.capabilities },
    isLoading: false,
    can: (capability: string) => auth.capabilities.includes(capability),
  }),
}));

function definition(
  overrides: Partial<FormDefinitionSummary>,
): FormDefinitionSummary {
  return {
    slug: "mock-interview",
    name: "Mock interview",
    entity: "activity",
    status: "active",
    published_version: { id: "v1", number: 1, schema_hash: "abc", field_count: 8 },
    draft_version: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.capabilities = ["form.view", "form.manage"];
});

describe("FormsPage", () => {
  it("shows a loading state", () => {
    useApi.mockReturnValue({ data: null, error: null, isLoading: true, reload: vi.fn() });
    render(<FormsPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state with a New form action", () => {
    const empty: FormDefinitionListResponse = { results: [] };
    useApi.mockReturnValue({ data: empty, error: null, isLoading: false, reload: vi.fn() });
    render(<FormsPage />);
    expect(screen.getByText("No forms yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /new form/i }).length).toBeGreaterThan(0);
  });

  it("shows an error state with retry", () => {
    const reload = vi.fn();
    useApi.mockReturnValue({
      data: null,
      error: new ApiError(500, "server_error", "Could not load forms.", "req-1"),
      isLoading: false,
      reload,
    });
    render(<FormsPage />);
    expect(screen.getAllByText(/could not load forms/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(reload).toHaveBeenCalled();
  });

  it("hides the page from a caller without form.view", () => {
    auth.capabilities = [];
    useApi.mockReturnValue({ data: null, error: null, isLoading: true, reload: vi.fn() });
    render(<FormsPage />);
    expect(screen.getByText(/do not have access/i)).toBeInTheDocument();
    expect(screen.queryByText("Forms")).not.toBeInTheDocument();
  });

  it("lists definitions with published/draft version chips", () => {
    const data: FormDefinitionListResponse = {
      results: [
        definition({}),
        definition({
          slug: "student-custom",
          name: "Student custom fields",
          entity: "student",
          published_version: null,
          draft_version: { id: "d1", number: 1, schema_hash: "xyz", field_count: 0 },
        }),
      ],
    };
    useApi.mockReturnValue({ data, error: null, isLoading: false, reload: vi.fn() });
    render(<FormsPage />);
    expect(screen.getByRole("link", { name: "Mock interview" })).toHaveAttribute(
      "href",
      "/admin/forms/mock-interview",
    );
    expect(screen.getByText(/v1 · 8 fields/)).toBeInTheDocument();
    expect(screen.getAllByText("None").length).toBeGreaterThan(0);
  });

  it("creates a new form and navigates to its detail page", async () => {
    const data: FormDefinitionListResponse = { results: [] };
    useApi.mockReturnValue({ data, error: null, isLoading: false, reload: vi.fn() });
    createFormDefinition.mockResolvedValue(
      definition({ slug: "new-form", name: "New form" }),
    );
    render(<FormsPage />);

    const [newFormButton] = screen.getAllByRole("button", { name: /new form/i });
    fireEvent.click(newFormButton!);
    fireEvent.change(screen.getByLabelText("Name", { exact: false }), {
      target: { value: "New form" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create form/i }));

    await waitFor(() =>
      expect(createFormDefinition).toHaveBeenCalledWith({
        slug: "new-form",
        name: "New form",
        entity: "activity",
      }),
    );
    expect(push).toHaveBeenCalledWith("/admin/forms/new-form?created=1");
  });
});
