/**
 * The trainer requirements board: a manager raises and closes, a trainer
 * answers, and `?open=` expands the one a notification pointed at.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequirementsBoard } from "@/components/requirements/requirements-board";
import type { TrainerRequirement } from "@/types/api";

const listRequirements = vi.hoisted(() => vi.fn());
const raiseRequirement = vi.hoisted(() => vi.fn());
const replyToRequirement = vi.hoisted(() => vi.fn());
const closeRequirement = vi.hoisted(() => vi.fn());
const removeRequirement = vi.hoisted(() => vi.fn());
vi.mock("@/lib/requirements", () => ({
  listRequirements,
  raiseRequirement,
  replyToRequirement,
  closeRequirement,
  removeRequirement,
}));

const listBatches = vi.hoisted(() => vi.fn());
vi.mock("@/lib/batches", () => ({ listBatches }));
const listTrainers = vi.hoisted(() => vi.fn());
vi.mock("@/lib/people", () => ({ listTrainers }));

const auth = vi.hoisted(() => ({
  value: {
    id: "u-manager",
    role: "manager",
    capabilities: ["requirement.manage"],
  },
}));
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({ user: auth.value, can: () => true }),
}));

const searchParams = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(searchParams.value),
  usePathname: () => "/requirements",
}));

function page(results: TrainerRequirement[]) {
  return {
    count: results.length,
    page: 1,
    page_size: 20,
    total_pages: 1,
    next: null,
    previous: null,
    results,
  };
}

function requirement(
  overrides: Partial<TrainerRequirement> = {},
): TrainerRequirement {
  return {
    id: "r1",
    title: "Cover Linux next week",
    details: "Monday to Friday, mornings.",
    status: "open",
    branch: "b1",
    branch_code: "MAIN",
    raised_by: "u-manager",
    raised_by_name: "Mira Manager",
    batch: "batch-1",
    batch_code: "LNX-01",
    batch_name: "Linux Essentials",
    needed_by: "2026-09-21",
    fulfilled_by: null,
    fulfilled_by_name: null,
    closed_at: null,
    closed_by_name: null,
    closing_note: "",
    reply_count: 1,
    replies: [
      {
        id: "rep1",
        author: "u-trainer",
        author_name: "Tina Trainer",
        author_role: "trainer",
        message: "I can take it.",
        created_at: "2026-09-14T10:00:00Z",
      },
    ],
    created_at: "2026-09-14T09:00:00Z",
    updated_at: "2026-09-14T10:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams.value = "";
  auth.value = {
    id: "u-manager",
    role: "manager",
    capabilities: ["requirement.manage"],
  };
  listBatches.mockResolvedValue(page([]));
  listTrainers.mockResolvedValue({
    ...page([]),
    results: [
      { id: "t1", user_id: "u-trainer", full_name: "Tina Trainer" },
      { id: "t2", user_id: "u-other", full_name: "Omar Other" },
    ],
  });
});

describe("RequirementsBoard", () => {
  it("lists open requirements with their badges and opens the one the address names", async () => {
    searchParams.value = "open=r1";
    listRequirements.mockResolvedValue(page([requirement()]));
    render(<RequirementsBoard />);

    expect(
      await screen.findByText("Cover Linux next week"),
    ).toBeInTheDocument();
    // The badge and the filter option both say it.
    expect(screen.getAllByText("Open").length).toBe(2);
    expect(screen.getByText("LNX-01")).toBeInTheDocument();
    expect(screen.getByText(/Needed by/)).toBeInTheDocument();
    // Expanded on arrival: the details and the reply are visible.
    expect(screen.getByText("Monday to Friday, mornings.")).toBeInTheDocument();
    expect(screen.getByText("I can take it.")).toBeInTheDocument();
    // Arriving from a notification shows everything, not only the open ones.
    expect(listRequirements).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "" }),
      expect.anything(),
    );
  });

  it("lets a manager raise one and tells them the trainers were told", async () => {
    listRequirements.mockResolvedValue(page([]));
    raiseRequirement.mockResolvedValue(
      requirement({ id: "r9", title: "Evening Python batch" }),
    );
    render(<RequirementsBoard />);
    expect(await screen.findByText("Nothing here")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Raise a requirement/ }),
    );
    fireEvent.change(screen.getByLabelText("What is needed"), {
      target: { value: "Evening Python batch" },
    });
    fireEvent.change(screen.getByLabelText("Needed by (optional)"), {
      target: { value: "2026-09-28" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Raise and tell the trainers" }),
    );

    await waitFor(() =>
      expect(raiseRequirement).toHaveBeenCalledWith({
        title: "Evening Python batch",
        details: "",
        batch: null,
        needed_by: "2026-09-28",
      }),
    );
    expect(
      await screen.findByText(/The trainers of your centre have been told/),
    ).toBeInTheDocument();
  });

  it("lets a trainer answer, and hides the manager controls from them", async () => {
    auth.value = { id: "u-trainer", role: "trainer", capabilities: [] };
    listRequirements.mockResolvedValue(
      page([requirement({ replies: [], reply_count: 0 })]),
    );
    replyToRequirement.mockResolvedValue({});
    render(<RequirementsBoard />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Cover Linux next week" }),
    );
    expect(
      screen.queryByRole("button", { name: /Raise a requirement/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Close this requirement" }),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Reply"), {
      target: { value: "Happy to." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Post reply" }));
    await waitFor(() =>
      expect(replyToRequirement).toHaveBeenCalledWith("r1", "Happy to."),
    );
    expect(
      await screen.findByText("Your reply has been posted."),
    ).toBeInTheDocument();
  });

  it("closes one naming the trainer who took it, answerers first", async () => {
    listRequirements.mockResolvedValue(page([requirement()]));
    closeRequirement.mockResolvedValue(
      requirement({
        status: "fulfilled",
        fulfilled_by: "t1",
        fulfilled_by_name: "Tina Trainer",
      }),
    );
    render(<RequirementsBoard />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Cover Linux next week" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Close this requirement" }),
    );
    const select = (await screen.findByLabelText(
      "Fulfilled by",
    )) as HTMLSelectElement;
    await waitFor(() => expect(select.options.length).toBe(3));
    expect(select.options[1]?.text).toBe("Tina Trainer (answered)");
    fireEvent.change(select, { target: { value: "t1" } });
    fireEvent.change(screen.getByLabelText("Note (optional)"), {
      target: { value: "Starts Monday." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Mark fulfilled" }));

    await waitFor(() =>
      expect(closeRequirement).toHaveBeenCalledWith("r1", {
        fulfilled_by: "t1",
        note: "Starts Monday.",
      }),
    );
    expect(
      await screen.findByText("Closed: fulfilled by Tina Trainer."),
    ).toBeInTheDocument();
  });

  it("shows a settled requirement without a reply box", async () => {
    listRequirements.mockResolvedValue(
      page([
        requirement({
          status: "closed",
          closing_note: "Not needed after all.",
          closed_by_name: "Mira Manager",
        }),
      ]),
    );
    render(<RequirementsBoard />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Cover Linux next week" }),
    );
    expect(screen.getByText(/closed without a taker/)).toBeInTheDocument();
    expect(screen.getByText(/Not needed after all\./)).toBeInTheDocument();
    expect(screen.queryByLabelText("Reply")).not.toBeInTheDocument();
  });
});
