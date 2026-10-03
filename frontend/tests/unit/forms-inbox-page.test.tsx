/**
 * Forms (`/forms`) and one form sent to someone (`/forms/[id]`): the inbox's
 * loading, error, empty and populated states; "Fill in a form" only for
 * people who may send forms; submitting answers, with field errors mapped
 * back onto the questions.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FormsPage from "@/app/forms/page";
import { FormAssignmentScreen } from "@/components/forms/form-assignment-screen";
import { ApiError } from "@/lib/api";
import type { FormAssignment, FormAssignmentDetail, Paginated } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

const submitFormAssignment = vi.hoisted(() => vi.fn());
vi.mock("@/lib/forms", async () => {
  const actual = await vi.importActual<typeof import("@/lib/forms")>("@/lib/forms");
  return { ...actual, submitFormAssignment };
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const auth = vi.hoisted(() => ({ role: "trainer", capabilities: [] as string[] }));
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: auth.role, capabilities: auth.capabilities },
    isLoading: false,
    can: (capability: string) => auth.capabilities.includes(capability),
  }),
}));

function row(overrides: Partial<FormAssignment> = {}): FormAssignment {
  return {
    id: "a-1",
    form: { slug: "enquiry-follow-up", name: "Enquiry follow-up", entity: "enquiry" },
    version: 1,
    title: "Follow up Ravi Sharma",
    message: "Call within a day.",
    status: "pending",
    assigned_to: { id: "u-1", name: "Kiran Counsellor", role: "counsellor" },
    requested_by: null,
    student: null,
    due_at: "2026-10-02T10:00:00Z",
    submitted_at: null,
    cancelled_at: null,
    created_at: "2026-10-01T10:00:00Z",
    is_overdue: false,
    from_automation: true,
    can_submit: true,
    can_cancel: false,
    ...overrides,
  };
}

function page(results: FormAssignment[]): Paginated<FormAssignment> {
  return { count: results.length, next: null, previous: null, results } as Paginated<FormAssignment>;
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.role = "trainer";
  auth.capabilities = [];
});

describe("FormsPage", () => {
  it("shows a loading state", () => {
    useApi.mockReturnValue({ data: null, error: null, isLoading: true, reload: vi.fn() });
    render(<FormsPage />);
    expect(screen.getByText("Loading forms…")).toBeInTheDocument();
  });

  it("shows an error with a retry", () => {
    const reload = vi.fn();
    useApi.mockReturnValue({
      data: null,
      error: new ApiError(500, "internal_error", "Server unavailable", "req-1"),
      isLoading: false,
      reload,
    });
    render(<FormsPage />);
    expect(screen.getByText("Could not load forms")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(reload).toHaveBeenCalled();
  });

  it("shows an empty inbox", () => {
    useApi.mockReturnValue({ data: page([]), error: null, isLoading: false, reload: vi.fn() });
    render(<FormsPage />);
    expect(screen.getByText("Nothing to fill in")).toBeInTheDocument();
    // A trainer cannot send forms, so no "Fill in a form" and no tabs.
    expect(screen.queryByText("Fill in a form")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Sent" })).not.toBeInTheDocument();
  });

  it("lists forms to fill, marking automation and overdue", () => {
    useApi.mockReturnValue({
      data: page([row({ is_overdue: true })]),
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    render(<FormsPage />);
    const link = screen.getByRole("link", { name: "Follow up Ravi Sharma" });
    expect(link).toHaveAttribute("href", "/forms/a-1");
    expect(screen.getByText("Automation")).toBeInTheDocument();
    expect(screen.getByText("Overdue")).toBeInTheDocument();
  });

  it("offers forms to fill in directly to people who may send forms", () => {
    auth.role = "counsellor";
    auth.capabilities = ["form.assign", "form.view"];
    useApi.mockImplementation((path: string) =>
      path === "/api/v1/forms/fillable/"
        ? {
            data: [{ slug: "enquiry", name: "Enquiry", entity: "enquiry", version: 1 }],
            error: null,
            isLoading: false,
            reload: vi.fn(),
          }
        : { data: page([]), error: null, isLoading: false, reload: vi.fn() },
    );
    render(<FormsPage />);
    expect(screen.getByRole("link", { name: /Enquiry/ })).toHaveAttribute(
      "href",
      "/forms/fill/enquiry",
    );
    expect(screen.getByRole("tab", { name: "Sent" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "All at my centre" })).toBeInTheDocument();
  });
});

describe("FormAssignmentPage", () => {
  const DETAIL: FormAssignmentDetail = {
    ...row(),
    fields: [
      {
        id: "f-1",
        key: "call_status",
        label: "Call outcome",
        help: "",
        type: "select",
        required: true,
        order: 0,
        group: "",
        options: [
          { value: "connected", label: "Connected" },
          { value: "busy", label: "Busy" },
        ],
        validation: {},
        visible_to_student: false,
        performance_key: null,
        show_if: {},
      },
    ],
    values: null,
  };

  function renderPage() {
    return render(<FormAssignmentScreen id="a-1" />);
  }

  it("submits the answers", async () => {
    const reload = vi.fn();
    useApi.mockReturnValue({ data: DETAIL, error: null, isLoading: false, reload });
    submitFormAssignment.mockResolvedValue({ ...DETAIL, status: "submitted" });
    renderPage();

    fireEvent.change(await screen.findByLabelText(/Call outcome/), {
      target: { value: "connected" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() =>
      expect(submitFormAssignment).toHaveBeenCalledWith("a-1", { call_status: "connected" }),
    );
    expect(await screen.findByText("Submitted. Thank you.")).toBeInTheDocument();
    expect(reload).toHaveBeenCalled();
  });

  it("puts a field error on its question", async () => {
    useApi.mockReturnValue({ data: DETAIL, error: null, isLoading: false, reload: vi.fn() });
    submitFormAssignment.mockRejectedValue(
      new ApiError(400, "validation_error", "Invalid input.", "req-2", {
        call_status: ["This field is required."],
      }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Submit" }));
    expect(await screen.findByText("This field is required.")).toBeInTheDocument();
    expect(screen.getByText("Some answers need attention.")).toBeInTheDocument();
  });

  it("shows submitted answers read-only", async () => {
    useApi.mockReturnValue({
      data: {
        ...DETAIL,
        status: "submitted",
        can_submit: false,
        submitted_at: "2026-10-01T12:00:00Z",
        values: { call_status: "busy" },
      },
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    renderPage();
    const select = (await screen.findByLabelText(/Call outcome/)) as HTMLSelectElement;
    expect(select.value).toBe("busy");
    expect(select).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Submit" })).not.toBeInTheDocument();
  });
});
