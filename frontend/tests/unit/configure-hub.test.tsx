/**
 * The configuration hub, and the two things the sidebar re-cut has to keep true.
 *
 * The hub exists because fourteen settings screens were fourteen sidebar
 * lines under a heading that was really the leftovers. What is pinned here is
 * that it shows only what the person may actually open — a dead link in a hub
 * is worse than a missing one, because the hub is where somebody goes when
 * they already know the screen exists — and that the two screens which were
 * reachable only by typing a URL are now on it.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ConfigureHub, CONFIG_SECTIONS } from '@/app/admin/configure/page';
import { ADMIN_NAV } from '@/components/navigation';
import { Capability } from '@/lib/capabilities';

const can = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth: () => ({ can }) }));

function holding(...capabilities: string[]) {
  can.mockImplementation((capability: string) => capabilities.includes(capability));
}

describe('ConfigureHub', () => {
  it('shows a card only when the person may open the screen behind it', () => {
    holding(Capability.automationManage, Capability.settingsManage);
    render(<ConfigureHub />);

    expect(screen.getByRole('link', { name: /Automation/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Settings & lists/ })).toBeInTheDocument();
    // Held by nobody in this test, so these must not be rendered at all —
    // not rendered-and-disabled, which still tells somebody the screen exists.
    expect(screen.queryByRole('link', { name: /Roles & permissions/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Branding/ })).not.toBeInTheDocument();
  });

  it('drops a whole section when none of its cards survive', () => {
    holding(Capability.automationManage);
    render(<ConfigureHub />);

    expect(screen.getByText('What the product sends')).toBeInTheDocument();
    expect(screen.queryByText('Who may do what')).not.toBeInTheDocument();
  });

  it('carries the two screens that were reachable only by URL', () => {
    holding(Capability.categoryManage, Capability.recordViewDeleted);
    render(<ConfigureHub />);

    expect(screen.getByRole('link', { name: /Course categories/ })).toHaveAttribute(
      'href',
      '/admin/categories',
    );
    // System status needs no capability, so it is there for anybody who can
    // open the hub.
    expect(screen.getByRole('link', { name: /System status/ })).toHaveAttribute('href', '/status');
  });

  it('still has something on it for somebody holding nothing else', () => {
    // Opening the hub needs `organisation.view_any` and System status needs
    // nothing beyond that, so the hub is never blank and there is no empty
    // state to write.
    holding();
    render(<ConfigureHub />);

    expect(screen.getByRole('link', { name: /System status/ })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Automation/ })).not.toBeInTheDocument();
  });

  it('every card points somewhere, once', () => {
    const hrefs = CONFIG_SECTIONS.flatMap((section) => section.cards.map((card) => card.href));
    expect(new Set(hrefs).size).toBe(hrefs.length);
    for (const href of hrefs) expect(href.startsWith('/')).toBe(true);
  });
});

describe("the administrator's re-cut sidebar", () => {
  const items = ADMIN_NAV.flatMap((group) => group.items);
  const hrefs = items.map((item) => item.href);

  it('is a handful of working groups, not eleven', () => {
    expect(ADMIN_NAV.length).toBeLessThanOrEqual(8);

    // "Trainers" and "Calendar" were each a heading over a single link, and
    // "Institution" was the fourteen leftovers. All three are gone.
    const titles = ADMIN_NAV.map((group) => group.title);
    expect(titles).not.toContain('Trainers');
    expect(titles).not.toContain('Calendar');
    expect(titles).not.toContain('Institution');

    // The two groups that are deliberately one line each: Configure is a hub,
    // and Placement is a module that grows its own entries later.
    const singles = ADMIN_NAV.filter((group) => group.title && group.items.length === 1);
    expect(singles.map((group) => group.title).sort()).toEqual(['Configure', 'Placement']);
  });

  it('carries the links that were genuinely unreachable', () => {
    // Assignments, weekly tests and projects are *not* in this list: the
    // `/teaching` hub already lists them, and repeating a hub's contents in
    // the menu above it was removed on purpose by an earlier pass.
    for (const href of ['/discussions', '/needs-attention', '/students/new']) {
      expect(hrefs).toContain(href);
    }
    for (const href of ['/teaching/assignments', '/teaching/assessments', '/teaching/projects']) {
      expect(hrefs).not.toContain(href);
    }
  });

  it('collapses configuration to one line', () => {
    expect(hrefs).toContain('/admin/configure');
    // The screens behind the hub are not also in the sidebar: two doors onto
    // one screen is how a menu grows back.
    // Accounts are the one screen in both places, deliberately: it is daily
    // work as well as configuration. Everything else has exactly one door.
    for (const href of CONFIG_SECTIONS.flatMap((s) => s.cards.map((c) => c.href))) {
      if (href === '/admin/users') continue;
      expect(hrefs).not.toContain(href);
    }
  });

  it('does not open on the audit trail', () => {
    expect(ADMIN_NAV[0]?.items[0]?.href).not.toBe('/admin/activity');
    // It is still reachable — it moved to Insight, where a question asked
    // after the fact belongs.
    const insight = ADMIN_NAV.find((group) => group.title === 'Insight');
    expect(insight?.items.map((item) => item.href)).toContain('/admin/activity');
  });

  it('keeps every link capability-gated exactly as before', () => {
    const ungated = items.filter((item) => !item.capability && !item.scopedRoles);
    // The only ungated entries are the personal tail and the pages whose
    // authority is the caller's own record.
    expect(ungated.map((item) => item.href).sort()).toEqual(
      [
        '/announcements',
        '/courses',
        '/discussions',
        '/forms',
        '/needs-attention',
        '/notifications',
        '/profile',
      ].sort(),
    );
  });
});
