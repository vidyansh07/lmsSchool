'use client';

/**
 * Configuration: everything that changes how the product behaves.
 *
 * These fourteen screens used to be fourteen lines in the sidebar, under a
 * heading called "Institution" that was really the leftovers — the group an
 * administrator uses least often per visit and most often by name. Nobody
 * sets up automation and branding in the same minute, so settings-shaped work
 * earns one sidebar line and a destination rather than a seventh of the menu.
 *
 * Grouped by what each screen governs, not by which app owns it: who may do
 * what, what the product sends, how the institution runs, and the safety net.
 * Two of these screens — course categories and system status — were reachable
 * only by typing the URL, which is the other reason this page exists.
 *
 * Every card is gated by the capability its destination needs, so a composed
 * role sees a shorter hub rather than a dead link. The hub itself asks for
 * `organisation.view_any`, and System status needs nothing beyond that, so
 * there is always at least one card and no empty state to write.
 */

import Link from 'next/link';
import {
  Building2,
  ClipboardCheck,
  FileText,
  ListTodo,
  Palette,
  Plug,
  ScrollText,
  Send,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  ToggleLeft,
  Trash2,
  UsersRound,
  Workflow,
  Zap,
  type LucideIcon,
} from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { Capability, type CapabilityName } from '@/lib/capabilities';

type ConfigCard = {
  href: string;
  label: string;
  hint: string;
  icon: LucideIcon;
  /** Absent means everyone who can open the hub can open the card. */
  capability?: CapabilityName;
};

type ConfigSection = {
  title: string;
  /** What this group of screens governs, in one line. */
  description: string;
  accent: string;
  cards: ConfigCard[];
};

export const CONFIG_SECTIONS: ConfigSection[] = [
  {
    title: 'Who may do what',
    description: 'Accounts, the roles they hold, and the rules those roles work inside.',
    accent: 'text-people',
    cards: [
      {
        href: '/admin/users',
        label: 'User accounts',
        hint: 'Create, deactivate, change a role, revoke a session.',
        icon: UsersRound,
        capability: Capability.userViewAny,
      },
      {
        href: '/admin/roles',
        label: 'Roles & permissions',
        hint: 'The six built-in roles, and any an administrator composes.',
        icon: ShieldCheck,
        capability: Capability.roleView,
      },
      {
        href: '/admin/branches',
        label: 'Centres',
        hint: 'The institution’s centres, and who is attached to each.',
        icon: Building2,
        capability: Capability.organisationViewAny,
      },
      {
        href: '/admin/policies',
        label: 'Rules & policies',
        hint: 'The numbers the product enforces, with their history.',
        icon: ScrollText,
        capability: Capability.policyView,
      },
    ],
  },
  {
    title: 'What the product sends',
    description: 'Every message that leaves the building, and what makes it leave.',
    accent: 'text-admissions',
    cards: [
      {
        href: '/admin/communication',
        label: 'Message templates',
        hint: 'Write a version, preview it, test-send, publish.',
        icon: Send,
        capability: Capability.templateManage,
      },
      {
        href: '/admin/settings/messages',
        label: 'Message settings',
        hint: 'Which message goes out on which event, on which channel.',
        icon: ToggleLeft,
        capability: Capability.settingsManage,
      },
      {
        href: '/admin/automation',
        label: 'Automation',
        hint: 'Rules that act on their own. Dry-run one before it does.',
        icon: Zap,
        capability: Capability.automationManage,
      },
      {
        href: '/admin/integrations',
        label: 'Integrations',
        hint: 'API keys and webhooks, and what they have delivered.',
        icon: Plug,
        capability: Capability.integrationManage,
      },
    ],
  },
  {
    title: 'How the institution runs',
    description: 'The shape of the academic year, the lists everything else chooses from.',
    accent: 'text-academic',
    cards: [
      {
        href: '/admin/academics',
        label: 'Academic rules',
        hint: 'Terms, the calendar, grading.',
        icon: ClipboardCheck,
        capability: Capability.academicConfigure,
      },
      {
        href: '/admin/settings',
        label: 'Settings & lists',
        hint: 'Academic years, banks, payment categories, taxes.',
        icon: Settings2,
        capability: Capability.settingsManage,
      },
      {
        href: '/admin/categories',
        label: 'Course categories',
        hint: 'How the catalogue is divided.',
        icon: SlidersHorizontal,
        capability: Capability.categoryManage,
      },
      {
        href: '/admin/forms',
        label: 'Form builder',
        hint: 'The forms counsellors and trainers fill in.',
        icon: FileText,
        capability: Capability.formManage,
      },
      {
        href: '/admin/activity-types',
        label: 'Activity types',
        hint: 'What kinds of work exist, and the fields each asks for.',
        icon: ListTodo,
        capability: Capability.activityTypeManage,
      },
      {
        href: '/admin/branding',
        label: 'Branding',
        hint: 'The logo and the brand colour.',
        icon: Palette,
        capability: Capability.platformConfigure,
      },
    ],
  },
  {
    title: 'The safety net',
    description: 'What was deleted, and whether the machinery is answering.',
    accent: 'text-ink-muted',
    cards: [
      {
        href: '/admin/recovery',
        label: 'Deleted records',
        hint: 'Restore something. Purging is a superadmin’s, and permanent.',
        icon: Trash2,
        capability: Capability.recordViewDeleted,
      },
      {
        href: '/status',
        label: 'System status',
        hint: 'Database, cache and mail, read live from the API.',
        icon: Workflow,
      },
    ],
  },
];

export default function ConfigurePage() {
  return (
    <RequireAuth capability={Capability.organisationViewAny}>
      <ConfigureHub />
    </RequireAuth>
  );
}

export function ConfigureHub() {
  const { can } = useAuth();

  const sections = CONFIG_SECTIONS.map((section) => ({
    ...section,
    cards: section.cards.filter((card) => !card.capability || can(card.capability)),
  })).filter((section) => section.cards.length > 0);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Configuration</h1>
        <p className="max-w-2xl text-sm text-ink-muted">
          Everything that changes how the product behaves, in one place. Only what you may change
          is shown.
        </p>
      </div>

      {sections.map((section) => (
        <section key={section.title} className="space-y-3">
          <div>
            <h2 className={`text-xs font-semibold uppercase tracking-wide ${section.accent}`}>
              {section.title}
            </h2>
            <p className="text-sm text-ink-muted">{section.description}</p>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {section.cards.map((card) => {
              const Icon = card.icon;
              return (
                <li key={card.href}>
                  <Link
                    href={card.href}
                    className="flex h-full gap-3 rounded-card border border-line bg-surface p-4 transition-colors hover:border-line-strong hover:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
                  >
                    <Icon className="mt-0.5 size-5 shrink-0 text-ink-faint" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block font-medium text-ink">{card.label}</span>
                      <span className="block text-sm text-ink-muted">{card.hint}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
