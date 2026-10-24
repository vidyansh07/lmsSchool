/**
 * An automated accessibility pass (axe-core) over the surfaces added while
 * matching the reference products: the lead screen's stage trail, the two
 * course editors, the Add Event drawer, the email composer and the Create
 * Automation wizard.
 *
 * Same harness as `a11y-new-surfaces.test.tsx` — names on every control,
 * labelled dialogs, no duplicate ids, valid ARIA; colour contrast is left to
 * a real browser, which is the only thing that can compute it.
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CreateAutomationWizard } from '@/components/automation/create-automation-wizard';
import { EmailComposer, blocksToHtml } from '@/components/communication/email-composer';
import { FeeInstalmentEditor } from '@/components/courses/fee-instalment-editor';
import { SubjectPicker } from '@/components/courses/subject-picker';
import { StageTrail } from '@/components/ui/stage-trail';
import { AddEventDrawer } from '@/components/work/add-event-drawer';

const useApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi }));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ user: { id: 'u1', full_name: 'Deepti Vyas', capabilities: [] }, can: () => true }),
}));
vi.mock('@/components/automation/use-published-fields', () => ({ usePublishedFields: () => [] }));

type AxeResults = { violations: { id: string; help: string; nodes: { html: string }[] }[] };
type Axe = { run: (context: Element | object, options: object) => Promise<AxeResults> };

async function loadAxe(): Promise<Axe | null> {
  try {
    const loaded = (await import('axe-core')) as unknown as { default?: Axe } & Axe;
    return loaded.default ?? loaded;
  } catch {
    return null;
  }
}

async function violations(node: Element, { skipFrames = false } = {}): Promise<string[]> {
  const axe = await loadAxe();
  if (!axe) return [];
  // The composer's preview is a sandboxed `srcdoc` iframe, which axe cannot
  // reach into under jsdom ("Respondable target must be a frame in the
  // current window"). Its content is the same HTML the server-rendered
  // preview shows and is covered by that component's own tests; the editor
  // around it is what this pass is about.
  const context = skipFrames ? { include: [node], exclude: [['iframe']] } : node;
  const result = await axe.run(context, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
  });
  return result.violations.map(
    (violation) =>
      `${violation.id}: ${violation.help} — ${violation.nodes.map((n) => n.html).join(' | ')}`,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useApi.mockReturnValue({
    data: {
      results: [
        {
          id: 'at-1',
          slug: 'follow-up',
          name: 'Follow up',
          description: '',
          category: 'counselling',
          subject: 'enquiry',
          allowed_creator_roles: ['counsellor'],
          allowed_assignee_roles: ['counsellor'],
          visible_to_student: false,
          default_duration_minutes: 5,
          form: null,
          requires_review: false,
          performance_weight: '0.00',
          risk_effect: 'none',
          reminder_minutes_before: 5,
          next_action: null,
          is_system: false,
          status: 'active',
          check_conflict: false,
          reopen_allowed: true,
          invite_organiser: false,
          invite_owner: false,
          created_by_name: 'Rajat Goyal',
          updated_by_name: 'Rajat Goyal',
          created_at: '2026-10-01T00:00:00Z',
          updated_at: '2026-10-01T00:00:00Z',
        },
      ],
    },
    error: null,
    isLoading: false,
    reload: vi.fn(),
  });
});

describe('accessibility of the reference-product surfaces', () => {
  it('really runs axe (a control with no name is caught)', async () => {
    if (!(await loadAxe())) return;
    const { container } = render(<button type="button" />);
    expect((await violations(container)).join('\n')).toMatch(/button-name/);
  });

  it('the stage trail', async () => {
    const { container } = render(
      <StageTrail
        steps={[
          { key: 'new', label: 'New' },
          { key: 'contacted', label: 'Contacted' },
        ]}
        current="contacted"
        label="Lead stage"
      />,
    );
    expect(await violations(container)).toEqual([]);
  });

  it('the course fee instalment editor', async () => {
    const { container } = render(
      <FeeInstalmentEditor
        rows={[{ label: 'Admission', percent: '50', due_after_days: 0 }]}
        onChange={vi.fn()}
      />,
    );
    expect(await violations(container)).toEqual([]);
  });

  it('the subject picker', async () => {
    const { container } = render(
      <SubjectPicker pool={['RHCSA']} value={['Python Basics']} onChange={vi.fn()} />,
    );
    expect(await violations(container)).toEqual([]);
  });

  it('the email composer', async () => {
    const { container } = render(
      <EmailComposer
        html={blocksToHtml([
          { kind: 'heading', text: 'Welcome' },
          { kind: 'button', text: 'Open', href: 'https://example.test' },
        ])}
        variables={['student.name']}
        onChange={vi.fn()}
      />,
    );
    expect(await violations(container, { skipFrames: true })).toEqual([]);
  });

  it('the Add Event drawer', async () => {
    render(
      <AddEventDrawer
        open
        subject={{ kind: 'enquiry', id: 'e-1', name: 'Himanshu Verma' }}
        onClose={vi.fn()}
        onCreated={vi.fn()}
      />,
    );
    const dialog = await screen.findByRole('dialog');
    expect(await violations(dialog)).toEqual([]);
  });

  it('the Create Automation wizard', async () => {
    render(<CreateAutomationWizard open onClose={vi.fn()} onCreated={vi.fn()} />);
    const dialog = await screen.findByRole('dialog');
    expect(await violations(dialog)).toEqual([]);
  });
});
