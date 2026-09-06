'use client';

/**
 * Application shell: skip link, navigation and content.
 *
 * Two layouts, because two jobs. Staff — administrators, managers and trainers —
 * work across thirty-odd screens all day, and a vertical sidebar holds that many
 * links in groups a person can scan without reading every word. A student has a
 * dozen pages and visits a few of them, so they keep a top bar: giving them a
 * sidebar would spend a fifth of a laptop screen on links they do not use.
 *
 * The navigation is presentational throughout. Which links a person sees comes
 * from the capability list the server returned; which requests succeed is
 * decided by the server on every call. Hiding a link is a courtesy, never a
 * permission.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, type ReactNode } from 'react';
import { Menu, X } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { STAFF_NAV, STAFF_ROLES, STUDENT_NAV, isVisible, type NavItem } from '@/components/navigation';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { env } from '@/lib/env';
import { cn } from '@/lib/utils';

/** Longest match wins, so `/teaching/projects` does not also light up `/teaching`. */
function useActiveHref(hrefs: string[]): string | null {
  const pathname = usePathname();
  let best: string | null = null;
  for (const href of hrefs) {
    const matches = href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`);
    if (matches && (best === null || href.length > best.length)) best = href;
  }
  return best;
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'block rounded-md px-3 py-2 text-sm transition-colors',
        'hover:bg-muted hover:text-foreground',
        // Marked two ways on purpose: colour alone is not a signal for everyone,
        // and the weight change survives a screenshot in greyscale.
        active
          ? 'bg-accent font-medium text-foreground'
          : 'text-muted-foreground',
      )}
    >
      {item.label}
    </Link>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2">
      <Link href="/" className="text-sm font-semibold tracking-tight">
        Grras <span className="text-primary">LMS</span>
      </Link>
      {env.appEnv !== 'production' ? (
        <Badge variant="warning" aria-label={`Environment: ${env.appEnv}`}>
          {env.appEnv}
        </Badge>
      ) : null}
    </div>
  );
}

function Account() {
  const { user, isLoading, signOut } = useAuth();
  if (isLoading) return null;
  if (!user) {
    return (
      <Button asChild size="sm">
        <Link href="/login">Sign in</Link>
      </Button>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-sm text-muted-foreground sm:inline">
        {user.full_name || user.email}
      </span>
      <Badge>{user.role}</Badge>
      <Button variant="outline" size="sm" onClick={() => void signOut()}>
        Sign out
      </Button>
    </div>
  );
}

function StaffLayout({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [openedAt, setOpenedAt] = useState(pathname);

  // Close the drawer on navigation: leaving it open over the page somebody just
  // asked for is the most irritating thing a mobile menu can do. Reset during
  // render rather than in an effect — the documented alternative to a
  // synchronous setState inside one, and the pattern used elsewhere here.
  if (openedAt !== pathname) {
    setOpenedAt(pathname);
    setOpen(false);
  }

  const groups = STAFF_NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => isVisible(item, user)),
  })).filter((group) => group.items.length > 0);

  const active = useActiveHref(groups.flatMap((group) => group.items.map((item) => item.href)));

  const sidebar = (
    <nav aria-label="Main" className="flex h-full flex-col gap-6 overflow-y-auto p-4">
      {groups.map((group, index) => (
        <div key={group.title ?? `group-${index}`} className="space-y-1">
          {/* Plain text, with no ARIA association to the list.
              As an <h2> it entered the document outline and competed with the
              page's own <h1>. Bound to the list with `aria-labelledby` it gave
              the <ul> an accessible name, and a list called "Courses and
              batches" then answered to a search for a form field named "Batch".
              The grouping here is visual; the links carry their own names, and
              the label is read in order like any other text. */}
          {group.title ? (
            <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {group.title}
            </p>
          ) : null}
          <ul className="space-y-0.5">
            {group.items.map((item) => (
              <li key={item.href}>
                <NavLink item={item} active={item.href === active} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_minmax(0,1fr)]">
      {/* Wide screens: the sidebar is simply there. */}
      <aside className="hidden border-r border-border bg-surface lg:block">
        <div className="sticky top-0 flex h-dvh flex-col">
          <div className="border-b border-border px-4 py-3">
            <Brand />
          </div>
          {sidebar}
        </div>
      </aside>

      <div className="flex min-h-dvh min-w-0 flex-col">
        <header className="border-b border-border bg-surface">
          <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
            <Button
              variant="outline"
              size="sm"
              className="lg:hidden"
              aria-expanded={open}
              aria-controls="staff-navigation"
              onClick={() => setOpen((current) => !current)}
            >
              {open ? (
                <X className="size-4" aria-hidden="true" />
              ) : (
                <Menu className="size-4" aria-hidden="true" />
              )}
              <span className="sr-only">{open ? 'Close the menu' : 'Open the menu'}</span>
            </Button>
            <div className="lg:hidden">
              <Brand />
            </div>
            <div className="ml-auto">
              <Account />
            </div>
          </div>
        </header>

        {/* Narrow screens: the same links, as a panel under the header. It is
            rendered rather than duplicated, so there is one list to maintain. */}
        {open ? (
          <div id="staff-navigation" className="border-b border-border bg-surface lg:hidden">
            {sidebar}
          </div>
        ) : null}

        <main id="main-content" className="w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
          {children}
        </main>
      </div>
    </div>
  );
}

function StudentLayout({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const items = STUDENT_NAV.filter((item) => isVisible(item, user));
  const active = useActiveHref(items.map((item) => item.href));

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <Brand />
          <nav aria-label="Main" className="ml-auto">
            <ul className="flex flex-wrap items-center gap-1">
              {items.map((item) => (
                <li key={item.href}>
                  <NavLink item={item} active={item.href === active} />
                </li>
              ))}
            </ul>
          </nav>
          <Account />
        </div>
      </header>

      <main id="main-content" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        {children}
      </main>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const isStaff = Boolean(user && STAFF_ROLES.includes(user.role));

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>
      {isStaff ? <StaffLayout>{children}</StaffLayout> : <StudentLayout>{children}</StudentLayout>}
    </>
  );
}
