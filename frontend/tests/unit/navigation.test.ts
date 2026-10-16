import { describe, expect, it } from "vitest";

import {
  ADMIN_NAV,
  COUNSELLOR_NAV,
  MANAGER_NAV,
  STAFF_NAV,
  STUDENT_NAV,
  STUDENT_NAV_GROUPS,
  SUPERADMIN_NAV,
  TRAINER_NAV,
  isVisible,
  navFor,
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
    expectUniqueDestinations(STAFF_NAV.flatMap((group) => group.items));
    expectUniqueDestinations(ADMIN_NAV.flatMap((group) => group.items));
    expectUniqueDestinations(SUPERADMIN_NAV.flatMap((group) => group.items));
    expectUniqueDestinations(MANAGER_NAV.flatMap((group) => group.items));
    expectUniqueDestinations(COUNSELLOR_NAV.flatMap((group) => group.items));
    expectUniqueDestinations(TRAINER_NAV.flatMap((group) => group.items));
    expectUniqueDestinations(STUDENT_NAV_GROUPS.flatMap((group) => group.items));
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
