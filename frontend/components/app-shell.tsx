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
 * The staff sidebar is simply present at `lg:` and wider — this is a desktop-
 * first operations tool. Below that it collapses into a `Sheet`: a real modal
 * drawer with its own focus trap, backdrop and Escape handling, rather than a
 * panel that pushes the page down. Because a `Sheet` covers the header while
 * open, the account controls (name, role, sign out) are reachable from inside
 * the drawer too, in its footer — closing the menu should never be the price
 * of signing out.
 *
 * The navigation is presentational throughout. Which links a person sees comes
 * from the capability list the server returned; which requests succeed is
 * decided by the server on every call. Hiding a link is a courtesy, never a
 * permission.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, type ReactNode } from 'react';
import { Menu } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { STAFF_NAV, STAFF_ROLES, STUDENT_NAV, isVisible, type NavItem } from '@/components/navigation';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet';
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
        'press relative block rounded-md py-2 pl-3.5 pr-3 text-sm transition-colors',
        'hover:bg-muted hover:text-foreground',
        // Marked three ways on purpose: colour alone is not a signal for
        // everyone, the weight change survives a screenshot in greyscale, and
        // the accent bar is a positional signal that needs no colour vision
        // at all.
        active
          ? cn(
              'bg-accent font-medium text-foreground',
              "before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-primary before:content-['']",
            )
          : 'text-muted-foreground',
      )}
    >
      {item.label}
    </Link>
  );
}

/** The wordmark plus a small decorative swatch in the true brand orange — the
 *  one place in the shell `--color-brand` appears, since it is a fill to look
 *  at, not text to read (see `globals.css`). The environment badge rides
 *  alongside it so a non-production build never looks like the real thing. */
function Brand() {
  return (
    <div className="flex items-center gap-2">
      <Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-tight">
        <span
          aria-hidden="true"
          className="size-2.5 shrink-0 rounded-full"
          style={{ backgroundColor: 'var(--color-brand)' }}
        />
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

/** First and last initial, for the avatar fallback — "Amy Admin" → "AA". */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  const first = parts[0]?.[0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : '';
  return (first + last).toUpperCase() || '?';
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
  const name = user.full_name || user.email;
  return (
    <div className="flex items-center gap-2.5">
      <Avatar size="sm" className="hidden sm:inline-flex">
        <AvatarFallback>{initials(name)}</AvatarFallback>
      </Avatar>
      <span className="hidden text-sm text-muted-foreground sm:inline">{name}</span>
      <Badge className="capitalize">{user.role}</Badge>
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

  const navGroups = (
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
          {navGroups}
        </div>
      </aside>

      <div className="flex min-h-dvh min-w-0 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-surface">
          <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
            <Button
              variant="outline"
              size="sm"
              className="lg:hidden"
              aria-label="Open navigation menu"
              onClick={() => setOpen(true)}
            >
              <Menu className="size-4" aria-hidden="true" />
            </Button>
            <div className="lg:hidden">
              <Brand />
            </div>
            <div className="ml-auto">
              <Account />
            </div>
          </div>
        </header>

        <main id="main-content" className="w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
          {children}
        </main>
      </div>

      {/* Narrow screens: the same links, in a real modal drawer rather than a
          panel that vanishes into "not there" — see the module docstring. */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent size="sm" className="flex flex-col">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="size-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: 'var(--color-brand)' }}
              />
              Grras <span className="text-primary">LMS</span>
            </SheetTitle>
          </SheetHeader>
          <div className="-mx-5 flex-1 overflow-y-auto border-y border-border">{navGroups}</div>
          <SheetFooter className="justify-start">
            <Account />
          </SheetFooter>
        </SheetContent>
      </Sheet>
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
