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
 *
 * The header's search control opens the command palette (`mod+k`,
 * DESIGN_DECISIONS.md "Navigation": "Search box in the top bar opens the
 * palette") rather than linking to a fixed screen as it once did — Phase 11
 * gives search somewhere real to go.
 *
 * The sidebar also has a second, collapsed state at `lg:` and wider: 5rem
 * (80px), icons only, each with its label as a `Tooltip`. A person's own
 * choice (a small edge-anchored toggle, persisted to `localStorage`) always
 * wins; absent one, it defaults to collapsed at `lg:` and expanded at `xl:`
 * — the breakpoint the sidebar exists at all is the one where screen width
 * is tightest, so that is where the narrower default belongs. Below `lg:`
 * none of this applies — the drawer (`Sheet`) always renders the sidebar's
 * full, expanded link labels, exactly as it did before this state existed.
 */
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';
import {
  Bell,
  ChevronRight,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
} from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { CommandPalette } from '@/components/command-palette';
import {
  navFor,
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
import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts';
import { useMediaQuery } from '@/hooks/use-media-query';
import { env } from '@/lib/env';
import { cn } from '@/lib/utils';

/** `localStorage` key for the sidebar's expanded/collapsed preference. Once a
 *  person picks one, it always wins over the breakpoint default below —
 *  see `useSidebarCollapsed`. */
const SIDEBAR_STORAGE_KEY = 'grras.sidebar-collapsed';

type SidebarPreference = 'expanded' | 'collapsed' | null;

function readSidebarPreference(): SidebarPreference {
  try {
    const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    return stored === 'expanded' || stored === 'collapsed' ? stored : null;
  } catch {
    return null;
  }
}

function writeSidebarPreference(value: 'expanded' | 'collapsed'): void {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, value);
  } catch {
    // No persistence available (private window, storage disabled). The
    // toggle still works for the rest of this session.
  }
}

/**
 * Expanded/collapsed, and the toggle that flips it.
 *
 * A person's own choice, once made, is final — it is read once as a lazy
 * initializer (the same "read an external value straight into state" trade
 * `data-table.tsx`'s density toggle makes: a server-rendered shell cannot
 * know a stored preference, so the very first paint falls back to the
 * breakpoint default below, which is an acceptable one-time mismatch for a
 * cosmetic layout preference). Absent a stored choice, the sidebar defaults
 * to collapsed at `lg:` (1024px, the narrow end of where it exists at all)
 * and expanded at `xl:` (1280px) — tracked live via `useMediaQuery` so
 * resizing across that line still updates the default for as long as nobody
 * has overridden it.
 */
function useSidebarCollapsed(): [boolean, () => void] {
  const [preference, setPreference] = useState<SidebarPreference>(() => readSidebarPreference());
  const isXlUp = useMediaQuery('(min-width: 80rem)');
  const collapsed = preference !== null ? preference === 'collapsed' : !isXlUp;

  function toggle() {
    const next: 'expanded' | 'collapsed' = collapsed ? 'expanded' : 'collapsed';
    setPreference(next);
    writeSidebarPreference(next);
  }

  return [collapsed, toggle];
}

/** Longest match wins, so `/teaching/projects` does not also light up `/teaching`. */
function useActiveHref(hrefs: string[]): string | null {
  const pathname = usePathname();
  let best: string | null = null;
  for (const href of hrefs) {
    const matches =
      href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`);
    if (matches && (best === null || href.length > best.length)) best = href;
  }
  return best;
}

function NavLink({ item, active, collapsed = false }: { item: NavItem; active: boolean; collapsed?: boolean }) {
  const Icon = item.icon;
  const link = (
    <Link
      href={item.href}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'group flex items-center gap-3 rounded-lg py-2 text-sm transition-colors duration-150',
        collapsed ? 'justify-center px-2' : 'px-3',
        'hover:bg-muted hover:text-foreground',
        // Marked three ways on purpose: colour alone is not a signal for
        // everyone, the weight change survives a screenshot in greyscale, and
        // the filled shape is a positional signal that needs no colour vision.
        active ? 'bg-accent font-semibold text-primary' : 'text-muted-foreground',
      )}
    >
      <Icon
        className={cn(
          'size-[18px] shrink-0 transition-colors duration-150',
          active ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground',
        )}
        strokeWidth={1.75}
        aria-hidden="true"
      />
      {/* Still in the DOM (and still the link's accessible name) when
          collapsed — only visually hidden, via the same `sr-only` utility
          `SheetTitle` and the skip link already use. The tooltip below is
          the sighted equivalent; a screen reader never loses the label. */}
      <span className={cn('truncate', collapsed && 'sr-only')}>{item.label}</span>
    </Link>
  );
  return collapsed ? (
    <Tooltip content={item.label} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  );
}

/**
 * The logo lockup. The mark is the one place `--color-brand` — the true Grras
 * orange — appears in the shell: it is a fill to look at, not text to read,
 * and it stays exactly this colour while every action in the product uses the
 * darker `--color-action`, which can carry a label. The environment badge
 * rides alongside so a
 * non-production build never looks like the real thing — the one thing this
 * component renders that is a safety signal rather than decoration, so it
 * survives `compact` in some form rather than simply vanishing with the
 * "Grras LMS" wordmark: a full pill has nowhere to go in a collapsed 80px
 * sidebar column, so it shrinks to a dot on the mark itself instead of
 * disappearing outright. (Pre-existing behaviour, unchanged here: the
 * compact mobile header bar still gets no badge at all — this only adds the
 * dot for the *desktop* collapsed sidebar, the one new `compact` caller this
 * phase adds.)
 */
function Brand({ compact = false, showEnvDot = false }: { compact?: boolean; showEnvDot?: boolean }) {
  const nonProduction = env.appEnv !== 'production';
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <Link href="/" className="relative flex min-w-0 items-center gap-2.5">
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-xl text-base font-bold text-white"
          style={{ backgroundColor: 'var(--color-brand)' }}
        >
          G
        </span>
        {compact ? (
          // The wordmark below is what normally gives this link its
          // accessible name; compact drops it for space, so without this the
          // link would announce as blank (the mark above is aria-hidden, and
          // the env dot — present only outside production — is a separate
          // signal, not a substitute for one). Same `sr-only` treatment
          // `NavLink`'s label gets when collapsed: gone visually, still the
          // name a screen reader reports.
          <span className="sr-only">Grras LMS — Home</span>
        ) : (
          <span className="flex min-w-0 flex-col leading-none">
            <span className="truncate text-base font-bold tracking-tight text-foreground">
              Grras
            </span>
            <span className="mt-0.5 text-2xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              LMS
            </span>
          </span>
        )}
        {compact && showEnvDot && nonProduction ? (
          <span
            role="img"
            aria-label={`Environment: ${env.appEnv}`}
            title={`Environment: ${env.appEnv}`}
            className="absolute -right-1 -top-1 size-2.5 rounded-full border-2 border-surface bg-amber"
          />
        ) : null}
      </Link>
      {nonProduction && !compact ? (
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
 *  sidebar: avatar, name, a second line, and a way out. Collapsed, it keeps
 *  only the avatar (its tooltip carries the name and role) and the sign-out
 *  control — the one workflow this card offers, so collapsing it can shrink
 *  the card but never drop what it does. */
function AccountCard({ collapsed = false }: { collapsed?: boolean }) {
  const { user, isLoading, signOut } = useAuth();
  // Nothing for a visitor: the header already offers "Sign in", and a second
  // copy in the sidebar is a second thing for a screen reader to announce and
  // a second button to keep in step. One way in.
  if (isLoading || !user) return null;
  const name = user.full_name || user.email;

  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-2">
        <Tooltip content={`${name} · ${user.role}`} side="right">
          {/* `tabIndex={0}` makes this the one collapsed tooltip trigger in
              this file that isn't already an interactive element (`Link`,
              `button`) — without it, `Tooltip`'s `onFocus`/`onBlur` pair
              never fires and a keyboard user can never reach this
              information at all, only a mouse can. It stays a plain `span`
              rather than a button: nothing happens on activation, so making
              it look actionable would be the wrong signal. */}
          <Avatar size="md" tabIndex={0} className="bg-accent text-primary">
            <AvatarFallback className="text-primary">{initials(name)}</AvatarFallback>
          </Avatar>
        </Tooltip>
        <Tooltip content="Sign out" side="right">
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

  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface p-2.5">
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
          <span className="text-xs capitalize text-muted-foreground">
            {user.role}
            {/* Which centre this account is bounded to. Only when there is one —
                a superadmin belongs to none, and "all of them" is not a value. */}
            {user.branch_name ? <span className="normal-case"> · {user.branch_name}</span> : null}
          </span>
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

/**
 * The link list itself, shared by the `lg:` sidebar (which passes its own
 * `collapsed` state) and the mobile drawer (which always passes `false` —
 * the drawer has the full width of a `Sheet` to work with and never needs
 * to shrink to icons).
 */
function NavGroups({
  groups,
  active,
  collapsed,
}: {
  groups: NavGroup[];
  active: string | null;
  collapsed: boolean;
}) {
  return (
    <nav
      aria-label="Main"
      className={cn('flex h-full flex-col gap-5 overflow-y-auto py-4', collapsed ? 'px-2' : 'px-3')}
    >
      {groups.map((group, index) => (
        <div key={group.title ?? `group-${index}`} className="space-y-1">
          {/* Plain text, with no ARIA association to the list.
              As an <h2> it entered the document outline and competed with the
              page's own <h1>. Bound to the list with `aria-labelledby` it gave
              the <ul> an accessible name, and a list called "Courses and
              batches" then answered to a search for a form field named "Batch".
              The grouping here is visual; the links carry their own names, and
              the label is read in order like any other text. Collapsed, the
              heading text itself would wrap or overflow an 80px column, so it
              is replaced with a plain divider — the links underneath still
              carry their own names either way. */}
          {group.title ? (
            collapsed ? (
              index > 0 ? <hr aria-hidden="true" className="mx-1 border-t border-border" /> : null
            ) : (
              <p className="px-3 pb-1.5 text-2xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                {group.title}
              </p>
            )
          ) : null}
          <ul className="space-y-0.5">
            {group.items.map((item) => (
              <li key={item.href}>
                <NavLink item={item} active={item.href === active} collapsed={collapsed} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/**
 * The expand/collapse control. Anchored to the sidebar's own edge rather
 * than squeezed into its 80px-wide collapsed header, which has no room left
 * for anything beside the brand mark — see the module docstring.
 */
function SidebarToggle({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const label = collapsed ? 'Expand navigation' : 'Collapse navigation';
  return (
    // The positioning lives on this wrapper, not the button itself: `Tooltip`
    // renders its own `relative` span around its child, which would otherwise
    // become the nearer positioned ancestor and anchor the button to itself
    // (a zero-sized box, since the button is the only thing giving it size)
    // instead of to `<aside>`'s own edge.
    <div className="absolute -right-3 top-5 z-10">
      <Tooltip content={label} side="right">
        <button
          type="button"
          onClick={onToggle}
          aria-label={label}
          aria-expanded={!collapsed}
          className="flex size-6 items-center justify-center rounded-full border border-border bg-surface text-muted-foreground transition-colors duration-150 hover:text-foreground"
        >
          <Icon className="size-3.5" aria-hidden="true" strokeWidth={2} />
        </button>
      </Tooltip>
    </div>
  );
}

function Shell({
  groups,
  onOpenSearch,
  children,
}: {
  groups: NavGroup[];
  /** Opens the command palette (Phase 11) — see the module docstring. */
  onOpenSearch: () => void;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [openedAt, setOpenedAt] = useState(pathname);
  const [collapsed, toggleCollapsed] = useSidebarCollapsed();

  // Close the drawer on navigation: leaving it open over the page somebody just
  // asked for is the most irritating thing a mobile menu can do. Reset during
  // render rather than in an effect — the documented alternative to a
  // synchronous setState inside one, and the pattern used elsewhere here.
  if (openedAt !== pathname) {
    setOpenedAt(pathname);
    setOpen(false);
  }

  const active = useActiveHref(groups.flatMap((group) => group.items.map((item) => item.href)));

  return (
    <div className="min-h-dvh bg-background lg:flex">
      {/* Wide screens: the sidebar is simply there, at 17rem or, collapsed,
          5rem (80px) — a plain `width` transition. `globals.css`'s own
          motion-utilities docstring says to animate only `transform` and
          `opacity`, and this is a deliberate, considered exception to that,
          not an oversight: a `transform`-based collapse was evaluated and
          rejected. Scaling the `<aside>` itself (as `ui/progress.tsx` does
          for its fill) only fakes the box's own size — the sibling that
          actually needs to grow into the reclaimed width is the `<main>`
          column next to it, and there is no way to animate *that* via
          `transform` without also scaling everything a page renders inside
          it, on every route this shell wraps, which trades one reflow for a
          real visual defect. The only real reflow-free route is Motion's
          `layout` animation system, which needs the `domMax` feature bundle
          — see `motion-config.tsx`'s own case for staying on the smaller
          `domAnimation` one instead. What is left is a `width` transition
          scoped to exactly the two flex children it has to touch (not
          `transition-all`), triggered by a person's own click rather than
          on every render — GPU-cheap enough for that, and left alone entirely
          under `prefers-reduced-motion` by the same global rule every other
          `transition-*` utility in this file already answers to (see
          `globals.css`), the same mechanism the R2 chart components and
          `Sparkline` opt into explicitly via `useReducedMotion` for their
          own JS-driven motion. */}
      <aside
        className={cn(
          'relative hidden shrink-0 border-r border-border bg-surface transition-[width] duration-200 lg:block',
          collapsed ? 'lg:w-20' : 'lg:w-[17rem]',
        )}
      >
        {/* No `overflow-hidden` here: the collapsed sidebar's nav-item
            tooltips (`side="right"`) are positioned `left-full` off an icon
            near the sidebar's *left* edge, so they land past this column's
            own right edge on purpose — clip that and a collapsed tooltip
            would be cut off exactly where it needs to be readable. The
            content itself never overflows horizontally either way (each
            state is a fixed layout, not something that grows mid-transition),
            so there is nothing here that actually needs containing. */}
        <div className="sticky top-0 flex h-dvh flex-col">
          <div
            className={cn(
              'flex h-16 shrink-0 items-center border-b border-border',
              collapsed ? 'justify-center px-2' : 'px-5',
            )}
          >
            <Brand compact={collapsed} showEnvDot={collapsed} />
          </div>
          <NavGroups groups={groups} active={active} collapsed={collapsed} />
          <div className={cn('border-t border-border', collapsed ? 'p-2' : 'p-3')}>
            <AccountCard collapsed={collapsed} />
          </div>
        </div>
        <SidebarToggle collapsed={collapsed} onToggle={toggleCollapsed} />
      </aside>

      <div className="flex min-h-dvh min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
            <Button
              variant="ghost"
              size="sm"
              className="size-9 p-0 text-muted-foreground lg:hidden"
              aria-label="Open navigation menu"
              onClick={() => setOpen(true)}
            >
              {/* size-[18px], matching Search/Bell/Settings below — this was
                  the one real icon-size inconsistency found in the header
                  (was size-5/20px, the only header control not on the same
                  18px scale as every other icon in an identical size-9
                  button). */}
              <Menu className="size-[18px]" aria-hidden="true" />
            </Button>
            <div className="lg:hidden">
              <Brand compact />
            </div>
            <Breadcrumb groups={groups} active={active} />
            <div className="ml-auto flex items-center gap-1 sm:gap-2">
              {/* Opens the command palette (Phase 11) — the tooltip carries
                  the chord so the shortcut is discoverable without a person
                  ever having to click this at all. */}
              <Tooltip content="Search (Ctrl/⌘K)">
                <Button
                  variant="ghost"
                  size="sm"
                  className="size-9 p-0 text-muted-foreground"
                  aria-label="Search"
                  onClick={onOpenSearch}
                >
                  <Search className="size-[18px]" aria-hidden="true" />
                </Button>
              </Tooltip>
              <HeaderAccount />
            </div>
          </div>
        </header>

        {/* tabIndex={-1} so the skip link's fragment navigation actually
            moves DOM focus here (a non-natively-focusable element like
            <main> only gets a "sequential focus navigation starting point"
            otherwise, which some browsers never turn into a real focus/
            arrival announcement for assistive tech). No outline-none: the
            skip link is activated from the keyboard, so this focus arrival
            gets the same global :focus-visible ring (globals.css) as every
            other focusable element -- the visible landing cue keyboard
            users need, not something to suppress. */}
        <main
          id="main-content"
          tabIndex={-1}
          className="w-full max-w-[90rem] flex-1 px-4 py-6 sm:px-6 lg:px-8"
        >
          {children}
        </main>
      </div>

      {/* Narrow screens: the same links, in a real modal drawer rather than a
          panel that vanishes into "not there" — see the module docstring.
          Always the expanded link list (`collapsed={false}`) — the icon-only
          state exists to save width on a screen that already has a sidebar,
          which is not what a `Sheet` drawer is for. */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent size="sm" className="flex flex-col">
          <SheetHeader>
            {/* The lockup is a link and a badge, which do not belong inside a
                heading element; the title is for the dialog's accessible name. */}
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <Brand />
          </SheetHeader>
          <div className="-mx-5 flex-1 overflow-y-auto border-y border-border">
            <NavGroups groups={groups} active={active} collapsed={false} />
          </div>
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
  const [paletteOpen, setPaletteOpen] = useState(false);

  // The one place `mod+k` is registered — every page under this shell shares
  // it, rather than each screen wiring its own copy of the same shortcut.
  useKeyboardShortcuts(
    [{ keys: 'mod+k', description: 'Open the command palette', handler: () => setPaletteOpen(true) }],
    Boolean(user),
  );

  // The student's links are a flat list; give them the one untitled group the
  // sidebar already knows how to draw, so both audiences share one shell.
  const groups: NavGroup[] = isStaff
    ? navFor(user?.role)
        .map((group) => ({
          ...group,
          items: group.items.filter((item) => isVisible(item, user)),
        }))
        .filter((group) => group.items.length > 0)
    : [{ items: STUDENT_NAV.filter((item) => isVisible(item, user)) }];

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>
      <Shell groups={groups} onOpenSearch={() => setPaletteOpen(true)}>
        {children}
      </Shell>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </>
  );
}
