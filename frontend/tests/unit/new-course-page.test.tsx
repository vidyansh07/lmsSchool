/**
 * New Course: one page for the course, the subjects it teaches and how its
 * fee is collected — and what it says when part of that saves and part
 * does not.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NewCoursePage from "@/app/admin/courses/new/page";
import { ApiError } from "@/lib/api";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const listCategories = vi.hoisted(() => vi.fn());
const listCourses = vi.hoisted(() => vi.fn());
const listModules = vi.hoisted(() => vi.fn());
const createCourse = vi.hoisted(() => vi.fn());
const createModule = vi.hoisted(() => vi.fn());
vi.mock("@/lib/courses", async () => {
  const actual = await vi.importActual<typeof import("@/lib/courses")>("@/lib/courses");
  return { ...actual, listCategories, listCourses, listModules, createCourse, createModule };
});

const setCourseInstalments = vi.hoisted(() => vi.fn());
vi.mock("@/lib/course-fees", async () => {
  const actual = await vi.importActual<typeof import("@/lib/course-fees")>("@/lib/course-fees");
  return { ...actual, setCourseInstalments };
});

vi.mock("@/components/require-auth", () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));

const CATEGORIES = {
  count: 1,
  page: 1,
  total_pages: 1,
  page_size: 100,
  next: null,
  previous: null,
  results: [
    { id: "cat-1", slug: "linux", name: "Linux", description: "", is_active: true, position: 0 },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  listCategories.mockResolvedValue(CATEGORIES);
  listCourses.mockResolvedValue({
    count: 1,
    page: 1,
    total_pages: 1,
    page_size: 5,
    next: null,
    previous: null,
    results: [{ id: "c-9", title: "Linux Essentials" }],
  });
  listModules.mockResolvedValue([
    { id: "m-1", title: "RHCSA", position: 0, status: "published", lessons: [] },
  ]);
  createCourse.mockResolvedValue({ id: "c-1", title: "Linux Advanced" });
  createModule.mockResolvedValue({ id: "m-9", title: "RHCE" });
  setCourseInstalments.mockResolvedValue([]);
});

async function fillTheBasics() {
  render(<NewCoursePage />);
  await screen.findByRole("option", { name: "Linux" });
  fireEvent.change(screen.getByRole("textbox", { name: "Course Name" }), {
    target: { value: "Linux Advanced" },
  });
}

describe("New Course", () => {
  it("borrows the subjects other courses under the standard already use", async () => {
    await fillTheBasics();
    // Spelled once, everywhere: the pool is what makes the two-column picker
    // worth having.
    expect(
      await screen.findByRole("button", { name: "RHCSA" }),
    ).toBeInTheDocument();
  });

  it("creates the course, then its subjects in the order shown", async () => {
    await fillTheBasics();

    const typed = screen.getByRole("textbox", { name: "Add a subject" });
    fireEvent.change(typed, { target: { value: "RHCE" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(typed, { target: { value: "Ansible" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    fireEvent.click(screen.getByRole("button", { name: "Create course" }));

    await waitFor(() =>
      expect(createCourse).toHaveBeenCalledWith(
        expect.objectContaining({ title: "Linux Advanced", category: "cat-1" }),
      ),
    );
    await waitFor(() => expect(createModule).toHaveBeenCalledTimes(2));
    expect(createModule.mock.calls.map(([, body]) => body.title)).toEqual(["RHCE", "Ansible"]);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/courses/c-1"));
  });

  it("moves a subject up, and saves them in that order", async () => {
    await fillTheBasics();
    const typed = screen.getByRole("textbox", { name: "Add a subject" });
    fireEvent.change(typed, { target: { value: "RHCE" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.change(typed, { target: { value: "Ansible" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    fireEvent.click(screen.getByRole("button", { name: "Ansible" }));
    fireEvent.click(screen.getByRole("button", { name: "Move the selected subject up" }));
    fireEvent.click(screen.getByRole("button", { name: "Create course" }));

    await waitFor(() => expect(createModule).toHaveBeenCalledTimes(2));
    expect(createModule.mock.calls.map(([, body]) => body.title)).toEqual(["Ansible", "RHCE"]);
  });

  it("borrows nothing when the standard has no sibling courses", async () => {
    listCourses.mockResolvedValue({
      count: 0,
      page: 1,
      total_pages: 1,
      page_size: 5,
      next: null,
      previous: null,
      results: [],
    });
    await fillTheBasics();

    expect(
      await screen.findByText(/Nothing to borrow — type the subjects below/),
    ).toBeInTheDocument();
  });

  it("keeps a typed subject out of the pool column once it is in the course", async () => {
    await fillTheBasics();
    await screen.findByRole("button", { name: "RHCSA" });

    const pool = within(screen.getByRole("list", { name: "Subjects used elsewhere" }));
    fireEvent.click(pool.getByRole("button", { name: "RHCSA" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Add the selected subject to this course" }),
    );

    expect(
      within(screen.getByRole("list", { name: "Subjects in this course" })).getByRole("button", {
        name: "RHCSA",
      }),
    ).toBeInTheDocument();
    // And it is no longer offered twice.
    expect(
      within(screen.getByRole("list", { name: "Subjects used elsewhere" })).queryByRole("button", {
        name: "RHCSA",
      }),
    ).not.toBeInTheDocument();
  });

  it("refuses a structure that does not add up before creating anything", async () => {
    await fillTheBasics();

    fireEvent.click(screen.getByRole("button", { name: /Add Fee Instalment/ }));
    fireEvent.change(screen.getByRole("spinbutton", { name: "Share (%)" }), {
      target: { value: "60" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create course" }));

    expect(await screen.findByText(/add up to 60.00%, not 100%/)).toBeInTheDocument();
    expect(createCourse).not.toHaveBeenCalled();
  });

  it("says what was saved and what was not when a subject fails", async () => {
    await fillTheBasics();
    createModule.mockRejectedValueOnce(
      new ApiError(400, "validation_error", "That title is already used.", "req-3"),
    );

    const typed = screen.getByRole("textbox", { name: "Add a subject" });
    fireEvent.change(typed, { target: { value: "RHCE" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(screen.getByRole("button", { name: "Create course" }));

    // The course exists; losing that to one bad row would be the worse answer.
    expect(
      await screen.findByText(/these subjects were not added: RHCE/),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
