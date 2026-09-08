'use client';

/**
 * Application shell: skip link, navigation and content.
 *
 * One layout for everybody, built to the admin reference the owner supplied:
 * a white sidebar of icon-and-label links in titled sections, the signed-in
 * person pinned to its foot, and a header carrying the breadcrumb and the
 * account controls. Students used to get a top bar instead — the reasoning
 * was that a dozen links did not deserve a sidebar — but the top bar wrapped
 * to five rows on a phone and ate a third of the screen, and a sidebar that
 * collapses into a drawer costs nothing on a phone at all.
 *
 * The sidebar is simply present at `lg:` and wider. Below that it becomes a
 * `Sheet`: a real modal drawer with its own focus trap, backdrop and Escape
 * handling, rather than a panel that pushes the page down. Because a `Sheet`
 * covers the header while open, the account controls are reachable from
 * inside the drawer too, in its footer — closing the menu should never be the
 * price of signing out.
 *
 * The navigation is presentational throughout. Which links a person sees comes
 * from the capability list the server returned; which requests succeed is
 * decided by the server on every call. Hiding a link is a courtesy, never a
 * permission.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, type ReactNode } from 'react';
import { Bell, ChevronRight, LogOut, Menu, Search, Settings } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import {
  STAFF_NAV,
  STAFF_ROLES,
  STUDENT_NAV,
  isVisible,
  type NavGroup,
  type NavItem,
} from '@/components/navigation';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Tooltip } from '@/components/ui/tooltip';
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
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'press group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-[var(--duration-quick)]',
        'hover:bg-muted hover:text-foreground',
        // Marked three ways on purpose: colour alone is not a signal for
        // everyone, the weight change survives a screenshot in greyscale, and
        // the filled shape is a positional signal that needs no colour vision.
        active ? 'bg-accent font-semibold text-primary' : 'text-muted-foreground',
      )}
    >
      <Icon
        className={cn(
          'size-[18px] shrink-0 transition-colors duration-[var(--duration-quick)]',
          active ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground',
        )}
        strokeWidth={1.75}
        aria-hidden="true"
      />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

/**
 * The logo lockup. The mark is the one place `--color-brand` — the true Grras
 * orange — appears in the shell: it is a fill to look at, not text to read,
 * and the owner asked for it to stay exactly this colour while the rest of the
 * interface went navy. The environment badge rides alongside so a
 * non-production build never looks like the real thing.
 */
function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <Link href="/" className="flex min-w-0 items-center gap-2.5">
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-xl text-base font-bold text-white shadow-[var(--shadow-card)]"
          style={{ backgroundColor: 'var(--color-brand)' }}
        >
          G
        </span>
        {compact ? null : (
          <span className="flex min-w-0 flex-col leading-none">
            <span className="truncate text-base font-bold tracking-tight text-foreground">Grras</span>
            <span className="mt-0.5 text-2xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              LMS
            </span>
          </span>
        )}
      </Link>
      {env.appEnv !== 'production' && !compact ? (
        <Badge variant="warning" dot={false} aria-label={`Environment: ${env.appEnv}`}>
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

/** The signed-in person, as the reference pins them to the foot of the
 *  sidebar: avatar, name, a second line, and a way out. */
function AccountCard() {
  const { user, isLoading, signOut } = useAuth();
  // Nothing for a visitor: the header already offers "Sign in", and a second
  // copy in the sidebar is a second thing for a screen reader to announce and
  // a second button to keep in step. One way in.
  if (isLoading || !user) return null;
  const name = user.full_name || user.email;
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface p-2.5 shadow-[var(--shadow-card)]">
      <Avatar size="md" className="bg-accent text-primary">
        <AvatarFallback className="text-primary">{initials(name)}</AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1 leading-tight">
        <p className="truncate text-sm font-semibold text-foreground">{name}</p>
        <p className="truncate text-xs capitalize text-muted-foreground">{user.role}</p>
      </div>
      <Tooltip content="Sign out">
        <Button
          variant="ghost"
          size="sm"
          className="size-8 shrink-0 p-0 text-muted-foreground hover:text-destructive"
          aria-label="Sign out"
          onClick={() => void signOut()}
        >
          <LogOut className="size-4" aria-hidden="true" />
        </Button>
      </Tooltip>
    </div>
  );
}

/** The header's right-hand cluster: the person, their role, and the two
 *  destinations every role shares. */
function HeaderAccount() {
  const { user, isLoading } = useAuth();
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
    <div className="flex items-center gap-1 sm:gap-2">
      <Tooltip content="Notifications">
        <Button asChild variant="ghost" size="sm" className="size-9 p-0 text-muted-foreground">
          <Link href="/notifications" aria-label="Notifications">
            <Bell className="size-[18px]" aria-hidden="true" />
          </Link>
        </Button>
      </Tooltip>
      <Tooltip content="Account settings">
        <Button asChild variant="ghost" size="sm" className="size-9 p-0 text-muted-foreground">
          <Link href="/settings/account" aria-label="Account settings">
            <Settings className="size-[18px]" aria-hidden="true" />
          </Link>
        </Button>
      </Tooltip>
      <Link
        href="/profile"
        className="ml-1 flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-2 transition-colors hover:bg-muted"
      >
        <Avatar size="sm" className="bg-accent">
          <AvatarFallback className="text-primary">{initials(name)}</AvatarFallback>
        </Avatar>
        <span className="hidden min-w-0 flex-col leading-tight md:flex">
          <span className="truncate text-sm font-semibold text-foreground">{name}</span>
          <span className="text-xs capitalize text-muted-foreground">{user.role}</span>
        </span>
      </Link>
    </div>
  );
}

/**
 * "Home › Section › Page", derived from the navigation rather than the URL, so
 * it names screens the way the sidebar does and never shows a raw slug.
 */
function Breadcrumb({ groups, active }: { groups: NavGroup[]; active: string | null }) {
  const group = groups.find((candidate) => candidate.items.some((item) => item.href === active));
  const item = group?.items.find((candidate) => candidate.href === active);
  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1.5 text-sm sm:flex">
      <Link href="/" className="text-muted-foreground transition-colors hover:text-foreground">
        Home
      </Link>
      {group?.title ? (
        <>
          <ChevronRight className="size-3.5 text-muted-foreground/60" aria-hidden="true" />
          <span className="text-muted-foreground">{group.title}</span>
        </>
      ) : null}
      {item ? (
        <>
          <ChevronRight className="size-3.5 text-muted-foreground/60" aria-hidden="true" />
          <span className="truncate font-medium text-foreground" aria-current="page">
            {item.label}
          </span>
        </>
      ) : null}
    </nav>
  );
}

function Shell({
  groups,
  searchHref,
  children,
}: {
  groups: NavGroup[];
  /** Where the header's search icon goes: the screen this role searches most. */
  searchHref: string;
  children: ReactNode;
}) {
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

  const active = useActiveHref(groups.flatMap((group) => group.items.map((item) => item.href)));

  const navGroups = (
    <nav aria-label="Main" className="flex h-full flex-col gap-5 overflow-y-auto px-3 py-4">
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
            <p className="px-3 pb-1.5 text-2xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
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
    <div className="min-h-dvh bg-background lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
      {/* Wide screens: the sidebar is simply there. */}
      <aside className="hidden border-r border-border bg-surface lg:block">
        <div className="sticky top-0 flex h-dvh flex-col">
          <div className="flex h-16 items-center border-b border-border px-5">
            <Brand />
          </div>
          {navGroups}
          <div className="border-t border-border p-3">
            <AccountCard />
          </div>
        </div>
      </aside>

      <div className="flex min-h-dvh min-w-0 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
            <Button
              variant="ghost"
              size="sm"
              className="size-9 p-0 text-muted-foreground lg:hidden"
              aria-label="Open navigation menu"
              onClick={() => setOpen(true)}
            >
              <Menu className="size-5" aria-hidden="true" />
            </Button>
            <div className="lg:hidden">
              <Brand compact />
            </div>
            <Breadcrumb groups={groups} active={active} />
            <div className="ml-auto flex items-center gap-1 sm:gap-2">
              {/* A destination, not a widget: the product's search lives on the
                  screens that have something to search, and this takes a
                  person to the one they most often want. */}
              <Tooltip content="Search">
                <Button asChild variant="ghost" size="sm" className="size-9 p-0 text-muted-foreground">
                  <Link href={searchHref} aria-label="Search">
                    <Search className="size-[18px]" aria-hidden="true" />
                  </Link>
                </Button>
              </Tooltip>
              <HeaderAccount />
            </div>
          </div>
        </header>

        <main id="main-content" className="w-full max-w-[90rem] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>

      {/* Narrow screens: the same links, in a real modal drawer rather than a
          panel that vanishes into "not there" — see the module docstring. */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent size="sm" className="flex flex-col">
          <SheetHeader>
            {/* The lockup is a link and a badge, which do not belong inside a
                heading element; the title is for the dialog's accessible name. */}
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <Brand />
          </SheetHeader>
          <div className="-mx-5 flex-1 overflow-y-auto border-y border-border">{navGroups}</div>
          <SheetFooter className="justify-start">
            <AccountCard />
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const isStaff = Boolean(user && STAFF_ROLES.includes(user.role));

  // The student's links are a flat list; give them the one untitled group the
  // sidebar already knows how to draw, so both audiences share one shell.
  const groups: NavGroup[] = isStaff
    ? STAFF_NAV.map((group) => ({
        ...group,
        items: group.items.filter((item) => isVisible(item, user)),
      })).filter((group) => group.items.length > 0)
    : [{ items: STUDENT_NAV.filter((item) => isVisible(item, user)) }];

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>
      <Shell groups={groups} searchHref={isStaff ? '/admin/students' : '/courses'}>
        {children}
      </Shell>
    </>
  );
}
