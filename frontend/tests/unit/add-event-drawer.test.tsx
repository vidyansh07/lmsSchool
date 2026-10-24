/**
 * Add Event: the drawer that books an event against a lead or a student.
 *
 * The three behaviours worth pinning: the subject line and the To time follow
 * the chosen event type until somebody edits them, the organiser cannot be
 * changed, and "reminder off" is sent as zero rather than left to the type's
 * default.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AddEventDrawer } from "@/components/work/add-event-drawer";
import type { ActivityType } from "@/types/api";

const useApi = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({ useApi }));

const createActivity = vi.hoisted(() => vi.fn());
vi.mock("@/lib/work", async () => {
  const actual = await vi.importActual<typeof import("@/lib/work")>("@/lib/work");
  return { ...actual, createActivity };
});

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { id: "u-1", full_name: "Deepti Vyas", capabilities: [] },
    can: () => true,
  }),
}));

// The drawer reads the event type's pinned form for its extra fields; this
// suite is about the drawer, so the form is empty.
vi.mock("@/components/automation/use-published-fields", () => ({
  usePublishedFields: () => [],
}));

function type(overrides: Partial<ActivityType> = {}): ActivityType {
  return {
    id: "at-1",
    slug: "technical-talk",
    name: "Technical Talk with Trainer",
    description: "",
    category: "mentoring",
    subject: "enquiry",
    allowed_creator_roles: ["counsellor"],
    allowed_assignee_roles: ["counsellor"],
    visible_to_student: false,
    default_duration_minutes: 5,
    form: null,
    requires_review: false,
    performance_weight: "0.00",
    risk_effect: "none",
    reminder_minutes_before: 5,
    next_action: null,
    is_system: false,
    status: "active",
    check_conflict: false,
    reopen_allowed: true,
    invite_organiser: false,
    invite_owner: false,
    created_by_name: "Rajat Goyal",
    updated_by_name: "Rajat Goyal",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...overrides,
  };
}

const SUBJECT = { kind: "enquiry" as const, id: "e-1", name: "Himanshu Verma" };

function renderDrawer() {
  return render(
    <AddEventDrawer open subject={SUBJECT} onClose={vi.fn()} onCreated={vi.fn()} />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useApi.mockReturnValue({
    data: { results: [type()] },
    error: null,
    isLoading: false,
    reload: vi.fn(),
  });
  createActivity.mockResolvedValue({ id: "a-1" });
});

describe("AddEventDrawer", () => {
  it("prefills the subject from the event and the lead, and lets it be changed", () => {
    renderDrawer();
    const subject = screen.getByRole("textbox", { name: "Subject" });
    expect(subject).toHaveValue("Technical Talk with Trainer: Himanshu Verma");

    fireEvent.change(subject, { target: { value: "Talk about CEH" } });
    expect(subject).toHaveValue("Talk about CEH");
  });

  it("ends the event after the type's own duration", async () => {
    renderDrawer();
    fireEvent.change(screen.getByLabelText(/^From/), {
      target: { value: "2026-10-23T18:50" },
    });
    expect(screen.getByLabelText(/^To/)).toHaveValue("2026-10-23T18:55");
    expect(screen.getByText(/5 minutes, from this event's settings/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() =>
      expect(createActivity).toHaveBeenCalledWith(
        expect.objectContaining({ duration_minutes: 5, enquiry: "e-1" }),
      ),
    );
  });

  it("stops following the duration once the To time is set by hand", () => {
    renderDrawer();
    fireEvent.change(screen.getByLabelText(/^From/), {
      target: { value: "2026-10-23T18:50" },
    });
    fireEvent.change(screen.getByLabelText(/^To/), { target: { value: "2026-10-23T20:00" } });
    expect(screen.getByLabelText(/^To/)).toHaveValue("2026-10-23T20:00");

    fireEvent.change(screen.getByLabelText(/^From/), {
      target: { value: "2026-10-23T19:00" },
    });
    // What the person typed wins over the type's default.
    expect(screen.getByLabelText(/^To/)).toHaveValue("2026-10-23T20:00");
  });

  it("refuses an event that ends before it starts", async () => {
    renderDrawer();
    fireEvent.change(screen.getByLabelText(/^From/), {
      target: { value: "2026-10-23T18:50" },
    });
    fireEvent.change(screen.getByLabelText(/^To/), { target: { value: "2026-10-23T17:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    expect(await screen.findByText("It cannot end before it starts.")).toBeInTheDocument();
    expect(createActivity).not.toHaveBeenCalled();
  });

  it("sends zero when the reminder is switched off", async () => {
    renderDrawer();
    fireEvent.click(screen.getByRole("switch", { name: "Reminder" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() =>
      expect(createActivity).toHaveBeenCalledWith(
        // Zero is this one event saying "no reminder"; leaving it out would
        // hand it back to the type's default.
        expect.objectContaining({ reminder_minutes_before: 0 }),
      ),
    );
  });

  it("will not let the organiser be changed, because the server sets it", () => {
    renderDrawer();
    expect(screen.getByLabelText(/Organiser/)).toBeDisabled();
    expect(screen.getByLabelText(/Organiser/)).toHaveValue("Deepti Vyas");
  });

  it("says so rather than offering an empty picker when no event is set up", () => {
    useApi.mockReturnValue({
      data: { results: [] },
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    renderDrawer();
    expect(screen.getByText("No events set up yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit" })).toBeDisabled();
  });

  it("offers only the events that apply to this kind of record", () => {
    useApi.mockReturnValue({
      data: {
        results: [
          type(),
          type({ slug: "mock-interview", name: "Mock Interview", subject: "student" }),
        ],
      },
      error: null,
      isLoading: false,
      reload: vi.fn(),
    });
    renderDrawer();

    expect(screen.getByRole("option", { name: "Technical Talk with Trainer" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Mock Interview" })).not.toBeInTheDocument();
  });
});
