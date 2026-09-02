'use client';

/**
 * Application shell: skip link, header, role-aware navigation and content.
 *
 * The navigation is presentational. Which links a user sees comes from the
 * capability list the server returned; which requests actually succeed is
 * decided by the server on every call. Hiding a link is a courtesy, never a
 * permission.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import { useAuth } from '@/components/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Capability } from '@/lib/capabilities';
import { env } from '@/lib/env';
import { cn } from '@/lib/utils';

interface NavItem {
  href: string;
  label: string;
  capability?: string;
  /** Show to trainers too, whose course rights come from per-course assignment. */
  roles?: string[];
}

const NAV_ITEMS: NavItem[] = [
  { href: '/dashboard', label: 'Dashboard', roles: ['student', 'trainer'] },
  { href: '/courses', label: 'Courses' },
  { href: '/my-batches', label: 'My batches', roles: ['student'] },
  { href: '/my-assignments', label: 'My assignments', roles: ['student'] },
  { href: '/my-attendance', label: 'My attendance', roles: ['student'] },
  { href: '/my-projects', label: 'My projects', roles: ['student'] },
  { href: '/my-learning', label: 'My learning', roles: ['student'] },
  { href: '/my-progress', label: 'My progress', roles: ['student'] },
  { href: '/my-results', label: 'My results', roles: ['student'] },
  { href: '/exams', label: 'Examinations', roles: ['student'] },
  { href: '/calendar', label: 'Calendar', roles: ['student', 'trainer'] },
  { href: '/announcements', label: 'Announcements' },
  { href: '/discussions', label: 'Discussions', roles: ['student', 'trainer'] },
  { href: '/notifications', label: 'Notifications' },
  // A trainer's daily driver. Staff who hold the session capability reach it
  // too; a trainer has no such capability, their authority is per batch.
  { href: '/teaching', label: 'Teaching', capability: Capability.sessionManageAny, roles: ['trainer'] },
  // Batches and authoring: administrators hold the capability; trainers reach
  // them because their rights come from per-record assignment, which no
  // capability reflects.
  { href: '/admin/overview', label: 'Overview', capability: Capability.reportViewAny },
  { href: '/admin/reports', label: 'Reports', capability: Capability.reportViewAny, roles: ['trainer'] },
  { href: '/admin/imports', label: 'Bulk import', capability: Capability.dataImport },
  { href: '/admin/batches', label: 'Batches', capability: Capability.batchViewAny, roles: ['trainer'] },
  { href: '/admin/courses', label: 'Authoring', capability: Capability.courseViewAny, roles: ['trainer'] },
  { href: '/admin/users', label: 'Users', capability: Capability.userViewAny },
  { href: '/admin/students', label: 'Students', capability: Capability.studentViewAny },
  { href: '/admin/trainers', label: 'Trainers', capability: Capability.trainerViewAny },
  { href: '/admin/academics', label: 'Academic rules', capability: Capability.academicConfigure },
  { href: '/admin/completions', label: 'Completions', capability: Capability.completionApprove },
  { href: '/admin/certificates', label: 'Certificates', capability: Capability.certificateManage },
  { href: '/profile', label: 'My profile' },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, isLoading, signOut } = useAuth();
  const pathname = usePathname();

  const visible = NAV_ITEMS.filter((item) => {
    // Role-only entries (no capability) are for the people that role serves.
    if (!item.capability) {
      return !item.roles || Boolean(user && item.roles.includes(user.role));
    }
    if (user?.capabilities.includes(item.capability)) return true;
    return Boolean(user && item.roles?.includes(user.role));
  });

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            Grras <span className="text-primary">LMS</span>
          </Link>
          {env.appEnv !== 'production' ? (
            <Badge variant="warning" aria-label={`Environment: ${env.appEnv}`}>
              {env.appEnv}
            </Badge>
          ) : null}

          <nav aria-label="Main" className="ml-auto">
            <ul className="flex flex-wrap items-center gap-1">
              {visible.map((item) => {
                const isActive =
                  item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={isActive ? 'page' : undefined}
                      className={cn(
                        'rounded-md px-3 py-1.5 text-sm transition-colors hover:bg-muted hover:text-foreground',
                        isActive ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground',
                      )}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          <div className="flex items-center gap-2">
            {isLoading ? null : user ? (
              <>
                <span className="hidden text-sm text-muted-foreground sm:inline">
                  {user.full_name || user.email}
                </span>
                <Badge>{user.role}</Badge>
                <Button variant="outline" size="sm" onClick={() => void signOut()}>
                  Sign out
                </Button>
              </>
            ) : (
              <Button asChild size="sm">
                <Link href="/login">Sign in</Link>
              </Button>
            )}
          </div>
        </div>
      </header>

      <main id="main-content" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        {children}
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto w-full max-w-6xl px-4 py-4 text-xs text-muted-foreground sm:px-6">
          Grras LMS — identity and people management (Phase 1).
        </div>
      </footer>
    </div>
  );
}
