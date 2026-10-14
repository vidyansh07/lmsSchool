import { describe, expect, it } from "vitest";

import {
  ADMIN_NAV,
  STAFF_NAV,
  STUDENT_NAV,
  isVisible,
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
