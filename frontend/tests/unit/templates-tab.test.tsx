/**
 * `components/communication/templates-tab.tsx` — migrated onto `DataTable`
 * (Phase R6). Covers what the migration must not have changed: every column
 * renders real data, the page request still goes through the same
 * `useApi`-backed path, and the density toggle persists.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TemplatesTab } from '@/components/communication/templates-tab';
import type { MessageTemplate, Paginated } from '@/types/api';

const useApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi }));

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

function page(results: MessageTemplate[]): Paginated<MessageTemplate> {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function templateRow(overrides: Partial<MessageTemplate> = {}): MessageTemplate {
  return {
    id: 't-1',
    key: 'batch_assigned',
    name: 'Batch assigned',
    channel: 'email',
    kind: 'batch.assigned',
    language: 'en',
    status: 'published',
    current_version: {
      id: 'v-1',
      template: 't-1',
      number: 2,
      subject: 'You have been assigned',
      body_html: '',
      body_text: '',
      variables: [],
      provider_template_id: '',
      approved_by: null,
      approved_at: '2026-08-01T00:00:00Z',
      published_at: '2026-08-02T00:00:00Z',
      created_at: '2026-07-01T00:00:00Z',
      updated_at: '2026-08-02T00:00:00Z',
    },
    draft_version: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

let lastPath = '';
function mockUseApi(data: Paginated<MessageTemplate> | null) {
  useApi.mockImplementation((path: string) => {
    lastPath = path;
    return { data, error: null, isLoading: false, reload: vi.fn() };
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  lastPath = '';
  useAuth.mockReturnValue({ user: { capabilities: ['template.manage'] } });
});

describe('TemplatesTab', () => {
  it('renders every column with real data', async () => {
    mockUseApi(page([templateRow()]));
    render(<TemplatesTab />);
    await waitFor(() => expect(screen.getByText('batch_assigned')).toBeInTheDocument());
    expect(screen.getByText('Batch assigned')).toBeInTheDocument();
    expect(screen.getByText('v2')).toBeInTheDocument();
  });

  it('requests the current page through the same path shape', () => {
    mockUseApi(page([templateRow()]));
    render(<TemplatesTab />);
    expect(lastPath).toBe('/api/v1/templates/?page=1');
  });

  it('shows the empty state with a create action when there are no templates', () => {
    mockUseApi(page([]));
    render(<TemplatesTab />);
    expect(screen.getByText('No templates yet')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /new template/i }).length).toBeGreaterThan(0);
  });

  it('persists the density toggle across a re-render', async () => {
    mockUseApi(page([templateRow()]));
    const { unmount } = render(<TemplatesTab />);
    await waitFor(() => expect(screen.getByText('batch_assigned')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /compact view/i }));
    expect(window.localStorage.getItem('grras.templates-density')).toBe('compact');
    unmount();

    render(<TemplatesTab />);
    await waitFor(() => expect(screen.getByText('batch_assigned')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /comfortable view/i })).toBeInTheDocument();
  });
});
