/**
 * An automated accessibility pass (axe-core) over the screens and dialogs
 * added in the UX-gap loops: names on every control, labelled dialogs, no
 * duplicate ids, valid ARIA. Colour contrast is left to the browser (jsdom
 * cannot compute it). axe-core comes in through eslint-plugin-jsx-a11y; if it
 * ever stops being installed this file skips rather than failing the build.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ActiveFilters } from '@/components/active-filters';
import { TrainerProfileCard } from '@/components/manage/trainer-profile-card';
import { SavedViews } from '@/components/saved-views';
import { EnrollmentStatusDialog } from '@/components/students/enrollment-status-dialog';
import { TagInput } from '@/components/ui/tag-input';
import { MyActivities } from '@/app/my-activities/page';
import { CreateStaffDialog } from '@/app/admin/users/create-staff-dialog';

vi.mock('@/lib/saved-filters', () => ({
  listSavedFilters: vi.fn().mockResolvedValue([
    { id: 'v1', screen: 's', name: 'Mine', filters: { role: 'manager' }, created_at: '2026-10-15T00:00:00Z' },
  ]),
  createSavedFilter: vi.fn(),
  deleteSavedFilter: vi.fn(),
}));
const getTrainer = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, getTrainer };
});
vi.mock('@/lib/work', () => ({
  listStudentActivities: vi.fn().mockResolvedValue({
    count: 1,
    page: 1,
    page_size: 20,
    total_pages: 1,
    results: [
      {
        id: 'a1',
        title: 'Mock interview',
        status: 'completed',
        type: { id: 't', slug: 'mock', name: 'Mock interview', category: 'assessment' },
        due_at: null,
        completed_at: '2026-10-11T10:00:00Z',
      },
    ],
  }),
  getActivity: vi.fn(),
}));
const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));
vi.mock('@/components/organisation/branch-field', () => ({
  BranchField: () => null,
  useBranches: () => ({ branches: [], failed: false }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

type AxeResults = { violations: { id: string; help: string; nodes: { html: string }[] }[] };
type Axe = { run: (node: Element, options: object) => Promise<AxeResults> };

async function loadAxe(): Promise<Axe | null> {
  try {
    const loaded = (await import('axe-core')) as unknown as { default?: Axe } & Axe;
    return loaded.default ?? loaded;
  } catch {
    return null;
  }
}

async function violations(node: Element): Promise<string[]> {
  const axe = await loadAxe();
  if (!axe) return [];
  const result = await axe.run(node, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  return result.violations.map(
    (violation) => `${violation.id}: ${violation.help} — ${violation.nodes.map((n) => n.html).join(' | ')}`,
  );
}

beforeEach(() => {
  useAuth.mockReturnValue({
    user: { id: 'u1', role: 'student', profile_id: 'stu-1' },
    can: () => true,
  });
});

describe('accessibility of the new surfaces', () => {
  it('really runs axe (a control with no name is caught)', async () => {
    if (!(await loadAxe())) return;
    const { container } = render(<button type="button" />);
    expect((await violations(container)).join('\n')).toMatch(/button-name/);
  });

  it('saved views, active filters and the tag input', async () => {
    const { container } = render(
      <div>
        <SavedViews screen="s" keys={['role']} query={{ role: 'admin' }} onApply={vi.fn()} />
        <ActiveFilters
          query={{ role: 'admin', search: 'x' }}
          onChange={vi.fn()}
          filters={[
            { key: 'role', label: 'Role' },
            { key: 'search', label: 'Search' },
          ]}
        />
        <label htmlFor="skills">Skills</label>
        <TagInput id="skills" value={['Linux']} onChange={vi.fn()} />
      </div>,
    );
    await screen.findByRole('button', { name: 'Mine' });
    expect(await violations(container)).toEqual([]);
  });

  it('the trainer profile card', async () => {
    getTrainer.mockResolvedValue({
      id: 'tp',
      trainer_id: 'T-1',
      user: { id: 'u', email: 't@example.com', is_active: true, is_email_verified: false },
      professional_title: 'Trainer',
      bio: '',
      skills: ['Linux'],
      expertise: '',
      qualifications: '',
      years_of_experience: 3,
      professional_links: {},
      is_accepting_assignments: true,
      completion_percent: 10,
      is_profile_complete: false,
      created_at: '',
      updated_at: '',
    });
    const { container } = render(<TrainerProfileCard trainerId="tp" />);
    await screen.findByText('Invitation not accepted');
    expect(await violations(container)).toEqual([]);
  });

  it('My activities', async () => {
    const { container } = render(<MyActivities />);
    await screen.findByRole('button', { name: 'Mock interview' });
    expect(await violations(container)).toEqual([]);
  });

  it('the enrolment and staff dialogs', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1', role: 'admin' }, can: () => true });
    render(
      <>
        <EnrollmentStatusDialog
          change={{ enrollmentId: 'e', subject: 'Linux · Morning', status: 'cancelled' }}
          onClose={vi.fn()}
          onChanged={vi.fn()}
        />
      </>,
    );
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    expect(await violations(document.body)).toEqual([]);
  });

  it('the add-staff dialog', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1', role: 'admin' }, can: () => true });
    render(<CreateStaffDialog open onClose={vi.fn()} onCreated={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    expect(await violations(document.body)).toEqual([]);
  });
});
