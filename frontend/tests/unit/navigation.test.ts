import { describe, expect, it } from "vitest";

import {
  ADMIN_NAV,
  STAFF_NAV,
  STUDENT_NAV,
  homeFor,
  isVisible,
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
  const assignments = itemAt(STAFF_NAV, "/teaching/assignments");

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
});

describe("navigation wording and structure", () => {
  it("uses distinct destinations in each navigation tree", () => {
    expectUniqueDestinations(STUDENT_NAV);
    expectUniqueDestinations(STAFF_NAV.flatMap((group) => group.items));
    expectUniqueDestinations(ADMIN_NAV.flatMap((group) => group.items));
  });

  it("uses the plain-language labels chosen for staging", () => {
    const labels = [...STUDENT_NAV, ...STAFF_NAV.flatMap((group) => group.items), ...ADMIN_NAV.flatMap((group) => group.items)].map(
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
