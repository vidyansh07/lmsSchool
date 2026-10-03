/**
 * Enquiries (`/enquiries`) and one enquiry (`/enquiries/[id]`): the
 * pipeline's loading, error, empty and populated states and its stage
 * filter; the enquiry's facts, moving its stage, and its activities.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EnquiriesPage from "@/app/enquiries/page";
import { EnquiryScreen } from "@/components/enquiries/enquiry-screen";
import { ApiError } from "@/lib/api";
import type { Enquiry, EnquiryDetail, Paginated } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

const updateEnquiry = vi.hoisted(() => vi.fn());
vi.mock("@/lib/enquiries", async () => {
  const actual = await vi.importActual<typeof import("@/lib/enquiries")>("@/lib/enquiries");
  return { ...actual, updateEnquiry };
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

vi.mock("@/components/work/activity-drawer", () => ({ ActivityDrawer: () => null }));

const auth = vi.hoisted(() => ({
  capabilities: ["enquiry.view_any", "enquiry.manage", "form.assign", "form.view"] as string[],
}));
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { id: "u-1", role: "counsellor", capabilities: auth.capabilities },
    isLoading: false,
    can: (capability: string) => auth.capabilities.includes(capability),
  }),
}));

function enquiry(overrides: Partial<EnquiryDetail> = {}): EnquiryDetail {
  return {
    id: "e-1",
    full_name: "Ravi Sharma",
    mobile: "+919876543210",
    email: "",
    whatsapp_number: "",
    state: "rajasthan",
    city: "jaipur",
    course: "devops",
    track: "devops_aws",
    preferred_centre: "jaipur",
    mode: "classroom",
    batch_timing: "evening",
    qualification: "graduate",
    source: "walk_in",
    utm_source: "",
    utm_medium: "",
    utm_campaign: "",
    remarks: "Wants weekend batch.",
    stage: "new",
    stage_changed_at: "2026-10-01T10:00:00Z",
    lost_reason: "",
    lead_quality: null,
    next_follow_up_at: null,
    last_contacted_at: null,
    owner: { id: "u-1", name: "Kiran Counsellor" },
    created_by: { id: "u-1", name: "Kiran Counsellor" },
    branch: { id: "b-1", name: "Main centre" },
    student: null,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    can_manage: true,
    history: [
      {
        id: "h-1",
        action: "enquiry.created",
        actor: "Kiran Counsellor",
        context: {},
        created_at: "2026-10-01T10:00:00Z",
      },
    ],
    ...overrides,
  };
}

function page<T>(results: T[]): Paginated<T> {
  return { count: results.length, next: null, previous: null, results } as Paginated<T>;
}

const SUMMARY = {
  stages: {
    new: 1,
    contacted: 0,
    interested: 0,
    counselling_booked: 0,
    demo_booked: 0,
    registered: 0,
    not_interested: 0,
    not_eligible: 0,
  },
  total: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EnquiriesPage", () => {
  function mockList(list: Partial<{ data: unknown; error: unknown; isLoading: boolean }>) {
    useApi.mockImplementation((path: string) =>
      path === "/api/v1/enquiries/summary/"
        ? { data: SUMMARY, error: null, isLoading: false, reload: vi.fn() }
        : { data: null, error: null, isLoading: false, reload: vi.fn(), ...list },
    );
  }

  it("shows a loading state", () => {
    mockList({ isLoading: true });
    render(<EnquiriesPage />);
    expect(screen.getByText("Loading enquiries…")).toBeInTheDocument();
  });

  it("shows an error", () => {
    mockList({ error: new ApiError(500, "internal_error", "Server unavailable", "req-1") });
    render(<EnquiriesPage />);
    expect(screen.getByText("Could not load enquiries")).toBeInTheDocument();
  });

  it("shows an empty pipeline", () => {
    mockList({ data: page<Enquiry>([]) });
    render(<EnquiriesPage />);
    expect(screen.getByText("No enquiries yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /new enquiry/i })).toHaveAttribute(
      "href",
      "/forms/fill/enquiry",
    );
  });

  it("lists enquiries and filters by stage", () => {
    mockList({ data: page<Enquiry>([enquiry()]) });
    render(<EnquiriesPage />);
    expect(screen.getByRole("link", { name: "Ravi Sharma" })).toHaveAttribute("href", "/enquiries/e-1");

    fireEvent.click(screen.getByRole("button", { name: /^Interested/ }));
    expect(useApi).toHaveBeenCalledWith("/api/v1/enquiries/?stage=interested");
  });
});

describe("EnquiryScreen", () => {
  function mockDetail(detail: EnquiryDetail, reload = vi.fn()) {
    useApi.mockImplementation((path: string) => {
      if (path === `/api/v1/enquiries/${detail.id}/`) {
        return { data: detail, error: null, isLoading: false, reload };
      }
      if (path.startsWith("/api/v1/activities/")) {
        return { data: page([]), error: null, isLoading: false, reload: vi.fn() };
      }
      if (path.startsWith("/api/v1/forms/assignments/")) {
        return { data: page([]), error: null, isLoading: false, reload: vi.fn() };
      }
      if (path === "/api/v1/activity-types/") {
        return { data: { results: [] }, error: null, isLoading: false, reload: vi.fn() };
      }
      throw new Error(`Unexpected useApi path: ${path}`);
    });
    return reload;
  }

  it("shows the enquiry and saves a stage change", async () => {
    const reload = mockDetail(enquiry());
    updateEnquiry.mockResolvedValue(enquiry({ stage: "interested" }));
    render(<EnquiryScreen id="e-1" />);

    expect(screen.getByRole("heading", { name: "Ravi Sharma" })).toBeInTheDocument();
    expect(screen.getByText("Wants weekend batch.")).toBeInTheDocument();
    expect(screen.getByText("No activities yet")).toBeInTheDocument();
    expect(screen.getByText("Enquiry created")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "interested" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(updateEnquiry).toHaveBeenCalledWith(
        "e-1",
        expect.objectContaining({ stage: "interested", lead_quality: null }),
      ),
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(reload).toHaveBeenCalled();
  });

  it("asks for a lost reason only for a lost stage", () => {
    mockDetail(enquiry());
    render(<EnquiryScreen id="e-1" />);
    expect(screen.queryByLabelText("Lost reason")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "not_interested" } });
    expect(screen.getByLabelText("Lost reason")).toBeInTheDocument();
  });

  it("is read-only for someone who cannot manage it", () => {
    mockDetail(enquiry({ can_manage: false, owner: { id: "u-9", name: "Someone" } }));
    render(<EnquiryScreen id="e-1" />);
    expect(screen.getByLabelText("Stage")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assign to me" })).not.toBeInTheDocument();
  });
});
