/**
 * The course catalogue as the reference product lists it, and the two things
 * its row menu does that nothing else in the app could: change a fee, and
 * delete a course.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminCoursesPage from "@/app/admin/courses/page";
import { ApiError } from "@/lib/api";
import type { CourseListRow, Paginated } from "@/types/api";

const useList = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-list", () => ({ useList }));

const setCourseStatus = vi.hoisted(() => vi.fn());
vi.mock("@/lib/courses", async () => {
  const actual = await vi.importActual<typeof import("@/lib/courses")>("@/lib/courses");
  return { ...actual, setCourseStatus };
});

const deleteCourse = vi.hoisted(() => vi.fn());
const listCoursePrices = vi.hoisted(() => vi.fn());
const listCourseInstalments = vi.hoisted(() => vi.fn());
const recordCoursePrice = vi.hoisted(() => vi.fn());
const setCourseInstalments = vi.hoisted(() => vi.fn());
vi.mock("@/lib/course-fees", async () => {
  const actual = await vi.importActual<typeof import("@/lib/course-fees")>("@/lib/course-fees");
  return {
    ...actual,
    deleteCourse,
    listCoursePrices,
    listCourseInstalments,
    recordCoursePrice,
    setCourseInstalments,
  };
});

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({ can: () => true, user: { capabilities: ["course.view_any"] } }),
}));
vi.mock("@/components/require-auth", () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/components/saved-views", () => ({ SavedViews: () => null }));

function course(overrides: Partial<CourseListRow> = {}): CourseListRow {
  return {
    id: "c-1",
    code: "GRS-C-0001",
    slug: "linux-essentials",
    title: "Linux Essentials",
    short_description: "",
    category_name: "Linux",
    category_slug: "linux",
    difficulty: "beginner",
    estimated_duration_minutes: 1200,
    default_fee: "25000.00",
    status: "published",
    visibility: "public",
    thumbnail_url: null,
    module_count: 4,
    lesson_count: 18,
    published_at: "2026-09-01T00:00:00Z",
    created_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

function page(results: CourseListRow[]): Paginated<CourseListRow> {
  return {
    count: results.length,
    page: 1,
    total_pages: 1,
    page_size: 20,
    next: null,
    previous: null,
    results,
  };
}

function mockList(results: CourseListRow[], query: Record<string, unknown> = {}) {
  const reload = vi.fn();
  const setQuery = vi.fn();
  useList.mockReturnValue({
    data: page(results),
    error: null,
    isLoading: false,
    reload,
    query,
    setQuery,
    setPage: vi.fn(),
  });
  return { reload, setQuery };
}

beforeEach(() => {
  vi.clearAllMocks();
  listCoursePrices.mockResolvedValue([]);
  listCourseInstalments.mockResolvedValue([]);
});

describe("the course catalogue", () => {
  it("counts the courses in the heading and lists them as rows", () => {
    mockList([course(), course({ id: "c-2", title: "Python Basics", category_name: "Python" })]);
    render(<AdminCoursesPage />);

    expect(screen.getByRole("heading", { name: /Courses \(2\)/ })).toBeInTheDocument();
    expect(screen.getByText("Linux Essentials")).toBeInTheDocument();
    expect(screen.getAllByText("Rs. 25,000")).toHaveLength(2);
  });

  it("asks the server for the active shelf rather than filtering rows away", () => {
    const { setQuery } = mockList([course()]);
    render(<AdminCoursesPage />);

    fireEvent.click(screen.getByRole("tab", { name: "Active" }));
    expect(setQuery).toHaveBeenCalledWith({ active: "true" });

    fireEvent.click(screen.getByRole("tab", { name: "Archived" }));
    expect(setQuery).toHaveBeenCalledWith({ active: "false" });
  });

  it("groups by standard, and drops the column that is then a heading", () => {
    mockList([course(), course({ id: "c-2", title: "Python Basics", category_name: "Python" })]);
    render(<AdminCoursesPage />);

    expect(screen.getByRole("columnheader", { name: "Standard" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "By standard" }));

    expect(screen.queryByRole("columnheader", { name: "Standard" })).not.toBeInTheDocument();
    expect(screen.getByText("Linux")).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
  });

  it("archives a course and says what archiving means", async () => {
    const { reload } = mockList([course()]);
    setCourseStatus.mockResolvedValue(course({ status: "archived" }));
    render(<AdminCoursesPage />);

    fireEvent.click(screen.getByRole("button", { name: /More actions for Linux Essentials/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Archive" }));

    await waitFor(() => expect(setCourseStatus).toHaveBeenCalledWith("c-1", "archived"));
    expect(await screen.findByText(/keeps everything and leaves the catalogue/)).toBeInTheDocument();
    expect(reload).toHaveBeenCalled();
  });

  it("offers Unarchive instead once a course is archived", async () => {
    mockList([course({ status: "archived" })]);
    setCourseStatus.mockResolvedValue(course({ status: "draft" }));
    render(<AdminCoursesPage />);

    fireEvent.click(screen.getByRole("button", { name: /More actions for Linux Essentials/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Unarchive" }));
    await waitFor(() => expect(setCourseStatus).toHaveBeenCalledWith("c-1", "draft"));
  });

  it("confirms a delete before making it", async () => {
    mockList([course()]);
    deleteCourse.mockResolvedValue(undefined);
    render(<AdminCoursesPage />);

    fireEvent.click(screen.getByRole("button", { name: /More actions for Linux Essentials/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    expect(deleteCourse).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete course" }));
    await waitFor(() => expect(deleteCourse).toHaveBeenCalledWith("c-1"));
  });

  it("shows the server's reason when a course cannot be deleted", async () => {
    mockList([course()]);
    deleteCourse.mockRejectedValue(
      new ApiError(
        409,
        "conflict",
        "This course cannot be deleted because 2 batch(es) run this course. Archive it instead, which keeps the record and takes it out of the catalogue.",
        "req-9",
      ),
    );
    render(<AdminCoursesPage />);

    fireEvent.click(screen.getByRole("button", { name: /More actions for Linux Essentials/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete course" }));

    expect(await screen.findByText(/Archive it instead/)).toBeInTheDocument();
  });
});

describe("Change Fees", () => {
  async function openFees() {
    render(<AdminCoursesPage />);
    fireEvent.click(screen.getByRole("button", { name: /Change Fees Linux Essentials/ }));
    return within(await screen.findByRole("dialog"));
  }

  it("records the new fee with the day it applies from, and the structure with it", async () => {
    mockList([course()]);
    recordCoursePrice.mockResolvedValue({
      id: "p-1",
      amount: "27000.00",
      effective_from: "2026-11-01",
      note: "Revised rate",
      recorded_by_name: "Rajat Goyal",
      created_at: "2026-10-24T00:00:00Z",
    });
    setCourseInstalments.mockResolvedValue([]);
    const dialog = await openFees();

    fireEvent.change(dialog.getByRole("spinbutton", { name: "Course fee" }), {
      target: { value: "27000" },
    });
    fireEvent.change(dialog.getByLabelText(/Effective from/), {
      target: { value: "2026-11-01" },
    });
    fireEvent.change(dialog.getByRole("textbox", { name: /Why it changed/ }), {
      target: { value: "Revised rate" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "Change Fees" }));

    await waitFor(() =>
      expect(recordCoursePrice).toHaveBeenCalledWith("c-1", {
        amount: "27000",
        effective_from: "2026-11-01",
        note: "Revised rate",
      }),
    );
  });

  it("refuses a structure that does not add up, before sending anything", async () => {
    mockList([course()]);
    const dialog = await openFees();

    fireEvent.click(dialog.getByRole("button", { name: /Add Fee Instalment/ }));
    fireEvent.change(dialog.getByRole("spinbutton", { name: "Share (%)" }), {
      target: { value: "40" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "Change Fees" }));

    expect(await dialog.findByText(/add up to 40.00%, not 100%/)).toBeInTheDocument();
    expect(recordCoursePrice).not.toHaveBeenCalled();
  });

  it("splits the shares evenly without leaving a hundredth behind", async () => {
    mockList([course()]);
    const dialog = await openFees();

    fireEvent.click(dialog.getByRole("button", { name: /Add Fee Instalment/ }));
    fireEvent.click(dialog.getByRole("button", { name: /Add Fee Instalment/ }));
    fireEvent.click(dialog.getByRole("button", { name: /Add Fee Instalment/ }));
    fireEvent.click(dialog.getByRole("button", { name: "Split evenly" }));

    const shares = dialog
      .getAllByRole("spinbutton", { name: "Share (%)" })
      .map((input) => (input as HTMLInputElement).value);
    expect(shares).toEqual(["33.34", "33.33", "33.33"]);
    expect(dialog.getByText(/add up to 100.00%/)).toBeInTheDocument();
  });
});
