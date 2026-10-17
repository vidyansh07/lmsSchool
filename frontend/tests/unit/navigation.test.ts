import { describe, expect, it } from "vitest";

import {
  ADMIN_NAV,
  COUNSELLOR_NAV,
  MANAGER_NAV,
  STUDENT_NAV,
  STUDENT_NAV_GROUPS,
  SUPERADMIN_NAV,
  TRAINER_NAV,
  homeFor,
  isVisible,
  navFor,
  safeReturnPath,
  type NavGroup,
  type NavItem,
} from "@/components/navigation";
import { Capability } from "@/lib/capabilities";

function itemAt(groups: NavGroup[], href: string): NavItem {
  const item = groups.flatMap((group) => group.items).find((entry) => entry.href === href);
  if (!item) throw new Error(`No navigation item for ${href}`);
  return item;
}

function expectUniqueDestinations(items: NavItem[]): void {
  const destinations = items.map((item) => item.href);
  expect(new Set(destinations).size).toBe(destinations.length);
}

describe("navigation authorization hints", () => {
  const assignments = itemAt(TRAINER_NAV, "/teaching/assignments");

  it("keeps assignment-scoped pages visible for the built-in trainer role", () => {
    expect(isVisible(assignments, { role: "trainer", capabilities: [] })).toBe(true);
  });

  it("does not restore a capability removed from a configured custom role", () => {
    expect(
      isVisible(assignments, {
        role: "trainer",
        custom_role: "limited-trainer",
        capabilities: [],
      }),
    ).toBe(false);
  });

  it("always honours an explicit capability", () => {
    expect(
      isVisible(assignments, {
        role: "trainer",
        custom_role: "assignment-trainer",
        capabilities: [Capability.assignmentManageAny],
      }),
    ).toBe(true);
  });

  it("includes the enquiries page in the administrator sidebar", () => {
    const enquiries = itemAt(ADMIN_NAV, "/enquiries");
    expect(enquiries.capability).toBe(Capability.enquiryViewAny);
  });

  it("shows fees only when the account holds fee visibility", () => {
    const fees = itemAt(COUNSELLOR_NAV, "/fees");
    expect(isVisible(fees, { role: "counsellor", capabilities: [] })).toBe(false);
    expect(
      isVisible(fees, {
        role: "counsellor",
        capabilities: [Capability.feeViewAny],
      }),
    ).toBe(true);
  });
});

describe("navigation wording and structure", () => {
  it("uses distinct destinations in each navigation tree", () => {
    expectUniqueDestinations(STUDENT_NAV);
    for (const nav of [
      ADMIN_NAV,
      SUPERADMIN_NAV,
      MANAGER_NAV,
      COUNSELLOR_NAV,
      TRAINER_NAV,
      STUDENT_NAV_GROUPS,
    ]) {
      expectUniqueDestinations(nav.flatMap((group) => group.items));
    }
  });

  it("uses the plain-language labels chosen for staging", () => {
    const labels = [
      ...STUDENT_NAV,
      ...[ADMIN_NAV, MANAGER_NAV, COUNSELLOR_NAV, TRAINER_NAV].flatMap((nav) =>
        nav.flatMap((group) => group.items),
      ),
    ].map(
      (item) => item.label,
    );

    expect(labels).toContain("Form inbox");
    expect(labels).toContain("Form builder");
    expect(labels).toContain("User accounts");
    expect(labels).toContain("Course catalogue");
    expect(labels).not.toContain("Examinations");
    expect(labels).not.toContain("Bulk import");
    expect(labels).not.toContain("Authoring");
  });

  it("ranks each role's daily workspace first", () => {
    expect(navFor("admin")[0]?.items[0]?.href).toBe("/admin/activity");
    expect(navFor("manager")[0]?.items[0]?.href).toBe("/manage");
    expect(navFor("counsellor")[0]?.items[0]?.href).toBe("/admissions/dashboard");
    expect(navFor("trainer")[0]?.items[0]?.href).toBe("/dashboard");
    expect(navFor("student")[0]?.items[0]?.href).toBe("/dashboard");
  });

  it("specializes manager and counsellor navigation despite their overlapping permissions", () => {
    expect(itemAt(MANAGER_NAV, "/manage/trainers")).toBeDefined();
    expect(itemAt(COUNSELLOR_NAV, "/fees")).toBeDefined();
    expect(COUNSELLOR_NAV.flatMap((group) => group.items).some((item) => item.href === "/manage/reviews")).toBe(false);
    expect(COUNSELLOR_NAV.flatMap((group) => group.items).some((item) => item.href === "/requirements")).toBe(false);
  });

  it("keeps a trainer's assigned-record work discoverable", () => {
    expect(itemAt(TRAINER_NAV, "/teaching/work").scopedRoles).toContain("trainer");
    expect(itemAt(TRAINER_NAV, "/dsr").scopedRoles).toContain("trainer");
    expect(
      TRAINER_NAV.flatMap((group) => group.items).some((item) => item.href === "/admin/users"),
    ).toBe(false);
  });
});

describe("a sidebar for each role", () => {
  const hrefs = (nav: NavGroup[]) => nav.flatMap((group) => group.items.map((item) => item.href));
  const titles = (nav: NavGroup[]) => nav.map((group) => group.title ?? "");

  it("gives each staff role its own sidebar", () => {
    expect(navFor("admin")).toBe(ADMIN_NAV);
    expect(navFor("superadmin")).toBe(SUPERADMIN_NAV);
    expect(navFor("student")).toBe(STUDENT_NAV_GROUPS);
    expect(navFor("manager")).toBe(MANAGER_NAV);
    expect(navFor("counsellor")).toBe(COUNSELLOR_NAV);
    expect(navFor("trainer")).toBe(TRAINER_NAV);
  });

  it("groups each one by the job its role does most", () => {
    expect(titles(MANAGER_NAV).slice(1, 3)).toEqual(["Academics", "Staff"]);
    expect(titles(COUNSELLOR_NAV).slice(1, 3)).toEqual(["Leads", "Admissions"]);
    expect(titles(TRAINER_NAV).slice(1, 2)).toEqual(["Classroom"]);
  });

  it("loses no page a manager or counsellor could reach before", () => {
    // Every screen the shared staff sidebar offered them is still in theirs.
    const shared = [
      "/activities",
      "/manage/batches",
      "/manage/trainers",
      "/manage/reviews",
      "/dsr",
      "/requirements",
      "/enquiries",
      "/admissions",
      "/admissions/new",
      "/admissions/batches",
      "/admissions/transfer",
      "/admin/users",
      "/admin/students",
      "/admin/courses",
      "/admin/batches",
      "/admin/completions",
      "/admin/certificates",
      "/admin/reports",
      "/admin/imports",
      "/calendar",
      "/announcements",
      "/forms",
      "/notifications",
      "/profile",
    ];
    for (const href of shared) expect(hrefs(MANAGER_NAV)).toContain(href);
    for (const href of ["/enquiries", "/admissions", "/admissions/new", "/admissions/transfer", "/admin/students", "/forms"]) {
      expect(hrefs(COUNSELLOR_NAV)).toContain(href);
    }
  });

  it("shows a trainer only the pages their role or capabilities reach", () => {
    const trainer = { role: "trainer", capabilities: [] as string[] };
    const visible = TRAINER_NAV.flatMap((group) => group.items).filter((item) =>
      isVisible(item, trainer),
    );
    expect(visible.map((item) => item.href)).toEqual(
      expect.arrayContaining(["/dashboard", "/teaching/today", "/teaching/assignments", "/admin/batches"]),
    );
    expect(visible.map((item) => item.href)).not.toContain("/admin/users");
  });

  it("hides a counsellor's page once a configured role takes its capability away", () => {
    const enquiries = itemAt(COUNSELLOR_NAV, "/enquiries");
    expect(
      isVisible(enquiries, { role: "counsellor", custom_role: "desk", capabilities: [] }),
    ).toBe(false);
  });
});

describe("homeFor", () => {
  it("starts each person at the first entry of their own navigation", () => {
    expect(homeFor({ role: "student", capabilities: [] })).toBe("/dashboard");
    expect(homeFor({ role: "trainer", capabilities: [] })).toBe("/dashboard");
    expect(
      homeFor({ role: "counsellor", capabilities: [Capability.enrolmentCreate] }),
    ).toBe("/admissions/dashboard");
    expect(
      homeFor({
        role: "admin",
        capabilities: [Capability.auditView, Capability.reportViewAny],
      }),
    ).toBe("/admin/activity");
    expect(
      homeFor({
        role: "manager",
        capabilities: [Capability.enrolmentCreate, Capability.performanceViewAny],
      }),
    ).toBe("/manage");
    expect(homeFor(null)).toBe("/login");
  });
});

describe("safeReturnPath", () => {
  it("keeps a path on this site and refuses everything else", () => {
    expect(safeReturnPath("/students/1?tab=fees")).toBe("/students/1?tab=fees");
    expect(safeReturnPath("https://evil.example")).toBeNull();
    expect(safeReturnPath("//evil.example")).toBeNull();
    expect(safeReturnPath("/\\evil.example")).toBeNull();
    expect(safeReturnPath("/login?next=/x")).toBeNull();
    expect(safeReturnPath("/ok\nSet-Cookie")).toBeNull();
    expect(safeReturnPath(null)).toBeNull();
  });
});
