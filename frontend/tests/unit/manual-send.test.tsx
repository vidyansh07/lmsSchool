/**
 * Manual send (`components/communication/manual-send.tsx`): the recipient
 * count is always fetched from the server before a send is allowed, sending
 * requires the exact count to be confirmed, and a stale-count `409` from the
 * real send is shown as its own "review again" state, never a generic error.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ManualSend } from '@/components/communication/manual-send';
import { ApiError } from '@/lib/api';
import type { BatchListRow, MessageTemplate, Paginated } from '@/types/api';

const useApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi }));

const previewCommunicationCount = vi.hoisted(() => vi.fn());
const sendCommunication = vi.hoisted(() => vi.fn());
vi.mock('@/lib/communication', async () => {
  const actual = await vi.importActual<typeof import('@/lib/communication')>('@/lib/communication');
  return { ...actual, previewCommunicationCount, sendCommunication };
});

vi.mock('@/lib/search', () => ({ search: vi.fn() }));

function templatePage(): Paginated<MessageTemplate> {
  const results: MessageTemplate[] = [
    {
      id: 'template-1',
      key: 'batch_assigned',
      name: 'Batch assigned',
      channel: 'email',
      kind: 'batch.assigned',
      language: 'en',
      status: 'published',
      current_version: {
        id: 'v1',
        template: 'batch_assigned',
        number: 1,
        subject: 'Welcome',
        body_html: '<p>Hi</p>',
        body_text: 'Hi',
        variables: [],
        provider_template_id: '',
        approved_by: 'admin-1',
        approved_at: '2026-09-01T00:00:00Z',
        published_at: '2026-09-01T00:00:00Z',
        created_at: '2026-09-01T00:00:00Z',
        updated_at: '2026-09-01T00:00:00Z',
      },
      draft_version: null,
      created_at: '2026-09-01T00:00:00Z',
      updated_at: '2026-09-01T00:00:00Z',
    },
  ];
  return { count: 1, page: 1, page_size: 25, total_pages: 1, next: null, previous: null, results };
}

function batchPage(): Paginated<BatchListRow> {
  const results: BatchListRow[] = [
    {
      id: 'batch-1',
      code: 'PY-101',
      name: 'Python mornings',
      course_id: 'course-1',
      course_code: 'PY',
      course_title: 'Python',
      course_slug: 'python',
      trainer_name: 'Ravi',
      start_date: '2026-09-01',
      end_date: '2026-12-01',
      capacity: 30,
      enrolled_count: 20,
      seats_available: 10,
      status: 'active',
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    } as BatchListRow,
  ];
  return { count: 1, page: 1, page_size: 100, total_pages: 1, next: null, previous: null, results };
}

function mockUseApi() {
  useApi.mockImplementation((path: string) => {
    if (path.startsWith('/api/v1/templates/')) {
      return { data: templatePage(), error: null, isLoading: false, reload: vi.fn() };
    }
    if (path.startsWith('/api/v1/batches/')) {
      return { data: batchPage(), error: null, isLoading: false, reload: vi.fn() };
    }
    throw new Error(`Unexpected useApi path: ${path}`);
  });
}

async function chooseTemplateAndBatch() {
  fireEvent.change(screen.getByLabelText('Template'), { target: { value: 'batch_assigned' } });
  fireEvent.change(screen.getByLabelText('Batch'), { target: { value: 'batch-1' } });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseApi();
});

describe('ManualSend — checking the count', () => {
  it('will not check until a template and a recipient are chosen', () => {
    render(<ManualSend />);
    expect(screen.getByRole('button', { name: /check recipient count/i })).toBeDisabled();
  });

  it('shows the server-resolved count and requires explicit confirmation to send', async () => {
    previewCommunicationCount.mockResolvedValue(42);
    render(<ManualSend />);
    await chooseTemplateAndBatch();

    fireEvent.click(screen.getByRole('button', { name: /check recipient count/i }));
    await waitFor(() =>
      expect(previewCommunicationCount).toHaveBeenCalledWith(
        expect.objectContaining({ channel: 'email', template: 'batch_assigned', recipients: { batch: 'batch-1' } }),
      ),
    );

    const confirm = await screen.findByTestId('send-count-confirm');
    expect(confirm).toHaveTextContent('42');
    // Not sent yet — only shown, never sent automatically.
    expect(sendCommunication).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /send to 42/i }));
    await waitFor(() =>
      expect(sendCommunication).toHaveBeenCalledWith(
        expect.objectContaining({ confirm_count: 42 }),
      ),
    );
  });

  it('shows a review-again state, not a generic error, on a stale-count 409', async () => {
    previewCommunicationCount.mockResolvedValueOnce(42).mockResolvedValueOnce(50);
    sendCommunication.mockRejectedValue(
      new ApiError(409, 'count_mismatch', 'The recipient count has changed.', 'req-1'),
    );
    render(<ManualSend />);
    await chooseTemplateAndBatch();

    fireEvent.click(screen.getByRole('button', { name: /check recipient count/i }));
    fireEvent.click(await screen.findByRole('button', { name: /send to 42/i }));

    const stale = await screen.findByTestId('send-count-stale');
    expect(stale).toHaveTextContent(/changed/i);
    expect(screen.queryByTestId('send-count-confirm')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /review again/i }));
    const confirm = await screen.findByTestId('send-count-confirm');
    expect(confirm).toHaveTextContent('50');
  });
});
