/**
 * The template builder (`/admin/communication/templates/[key]`): editing a
 * draft's variables allowlist, the Preview panel surfacing a warning for a
 * variable not on that allowlist, and approving a WhatsApp-channel template
 * requiring a step-up retry (same pattern as `components/roles/
 * step-up-dialog.tsx`).
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TemplateBuilder } from '@/components/communication/template-builder';
import type { MessageTemplate, TemplatePreviewResult, TemplateVersion } from '@/types/api';

const useApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi }));

const approveTemplateVersion = vi.hoisted(() => vi.fn());
const publishTemplateVersion = vi.hoisted(() => vi.fn());
const previewTemplateVersion = vi.hoisted(() => vi.fn());
const testSendTemplateVersion = vi.hoisted(() => vi.fn());
const updateTemplateVersion = vi.hoisted(() => vi.fn());
const createTemplateVersion = vi.hoisted(() => vi.fn());
vi.mock('@/lib/communication', async () => {
  const actual = await vi.importActual<typeof import('@/lib/communication')>('@/lib/communication');
  return {
    ...actual,
    approveTemplateVersion,
    publishTemplateVersion,
    previewTemplateVersion,
    testSendTemplateVersion,
    updateTemplateVersion,
    createTemplateVersion,
  };
});

const stepUpWithPassword = vi.hoisted(() => vi.fn());
vi.mock('@/lib/roles', async () => {
  const actual = await vi.importActual<typeof import('@/lib/roles')>('@/lib/roles');
  return { ...actual, stepUpWithPassword };
});

const auth = vi.hoisted(() => ({
  capabilities: ['template.manage', 'template.approve'] as string[],
}));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({
    user: { role: 'admin', capabilities: auth.capabilities },
    can: (capability: string) => auth.capabilities.includes(capability),
  }),
}));

function version(overrides: Partial<TemplateVersion> = {}): TemplateVersion {
  return {
    id: 'v1',
    template: 'batch_assigned',
    number: 1,
    subject: 'Welcome to {{ batch.name }}',
    body_html: '<p>Hi {{ student.name }}</p>',
    body_text: 'Hi {{ student.name }}',
    variables: ['student.name', 'batch.name'],
    provider_template_id: '',
    approved_by: null,
    approved_at: null,
    published_at: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

function template(overrides: Partial<MessageTemplate> = {}): MessageTemplate {
  return {
    id: 'template-1',
    key: 'batch_assigned',
    name: 'Batch assigned',
    channel: 'email',
    kind: 'batch.assigned',
    language: 'en',
    status: 'draft',
    current_version: null,
    draft_version: version(),
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

function mockUseApi(row: MessageTemplate, reload = vi.fn()) {
  useApi.mockImplementation((path: string) => {
    if (path === `/api/v1/templates/${row.key}/`) {
      return { data: row, error: null, isLoading: false, reload };
    }
    throw new Error(`Unexpected useApi path: ${path}`);
  });
  return reload;
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.capabilities = ['template.manage', 'template.approve'];
});

describe('TemplateBuilder — variables allowlist', () => {
  it('adds a variable once, ignoring a duplicate, and can remove one', () => {
    mockUseApi(template());
    render(<TemplateBuilder templateKey="batch_assigned" />);

    const list = screen.getByTestId('template-variables-list');
    expect(within(list).getByText('student.name')).toBeInTheDocument();
    expect(within(list).getByText('batch.name')).toBeInTheDocument();

    const input = screen.getByPlaceholderText('e.g. student.name');
    fireEvent.change(input, { target: { value: 'student.name' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    // Still exactly one "student.name" chip in the allowlist — a duplicate
    // add is a no-op, not a second chip.
    expect(within(list).getAllByText('student.name')).toHaveLength(1);

    fireEvent.change(input, { target: { value: 'trainer.name' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(within(list).getByText('trainer.name')).toBeInTheDocument();
    // Save draft only becomes available once something has actually changed.
    expect(screen.getByRole('button', { name: /save draft/i })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'Remove trainer.name' }));
    expect(within(list).queryByText('trainer.name')).not.toBeInTheDocument();
  });

  it('disables Save draft until something changes', () => {
    mockUseApi(template());
    render(<TemplateBuilder templateKey="batch_assigned" />);
    expect(screen.getByRole('button', { name: /save draft/i })).toBeDisabled();
  });

  it('offers "Start a new version" instead of an editor once nothing is in progress', () => {
    mockUseApi(
      template({
        status: 'published',
        draft_version: null,
        current_version: version({ published_at: '2026-09-05T00:00:00Z', approved_at: '2026-09-04T00:00:00Z' }),
      }),
    );
    render(<TemplateBuilder templateKey="batch_assigned" />);
    expect(screen.queryByRole('button', { name: /save draft/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start a new version/i })).toBeInTheDocument();
  });
});

describe('TemplateBuilder — preview', () => {
  it('renders a warning for a variable the body references but the allowlist does not have', async () => {
    mockUseApi(template());
    const result: TemplatePreviewResult = {
      subject: 'Welcome to Batch A',
      html: '<p>Hi Aisha</p>',
      text: 'Hi Aisha',
      warnings: ["'{{trainer.phone}}' is not in this version's variable allowlist."],
    };
    previewTemplateVersion.mockResolvedValue(result);

    render(<TemplateBuilder templateKey="batch_assigned" />);
    fireEvent.click(screen.getByRole('button', { name: /render preview/i }));

    await waitFor(() => expect(previewTemplateVersion).toHaveBeenCalledWith('batch_assigned', 1, {}));
    const warnings = await screen.findByTestId('preview-warnings');
    expect(within(warnings).getByText(/trainer\.phone/)).toBeInTheDocument();
    expect(screen.getByTestId('template-html-preview')).toBeInTheDocument();
  });
});

describe('TemplateBuilder — WhatsApp approval needs a step-up', () => {
  it('opens the step-up dialog on a step_up_required refusal and retries on success', async () => {
    mockUseApi(
      template({
        channel: 'whatsapp',
        draft_version: version({ provider_template_id: 'wa-123' }),
      }),
    );
    approveTemplateVersion
      .mockRejectedValueOnce({ code: 'step_up_required' })
      .mockResolvedValueOnce(version({ provider_template_id: 'wa-123', approved_by: 'admin-1', approved_at: '2026-09-02T00:00:00Z' }));
    stepUpWithPassword.mockResolvedValue(undefined);

    render(<TemplateBuilder templateKey="batch_assigned" />);
    fireEvent.click(screen.getByRole('button', { name: /^approve$/i }));

    await waitFor(() => expect(approveTemplateVersion).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Confirm it is you')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'hunter2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(stepUpWithPassword).toHaveBeenCalledWith('hunter2'));
    await waitFor(() => expect(approveTemplateVersion).toHaveBeenCalledTimes(2));
  });
});
