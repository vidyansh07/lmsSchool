/**
 * The Export menu: three formats; a small list downloads at once, a large one
 * is queued with a toast; nothing for somebody without the export right.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ExportMenu, INLINE_EXPORT_LIMIT } from '@/components/export-menu';

const queueExport = vi.hoisted(() => vi.fn());
const toast = vi.hoisted(() => vi.fn());
const canMock = vi.hoisted(() => ({ value: true }));

vi.mock('@/lib/reporting', async () => {
  const actual = await vi.importActual<typeof import('@/lib/reporting')>('@/lib/reporting');
  return { ...actual, queueExport };
});
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ toast }) }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => ({ can: () => canMock.value }) }));

describe('ExportMenu', () => {
  it('offers Excel, PDF and CSV and downloads a small list at once', async () => {
    const assign = vi.fn();
    Object.defineProperty(window, 'location', { value: { assign }, writable: true });
    render(<ExportMenu reportKey="students" filters={{ search: 'ra' }} count={12} />);
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    expect(await screen.findByRole('menuitem', { name: /excel/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /pdf/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('menuitem', { name: /csv/i }));
    await waitFor(() => expect(assign).toHaveBeenCalledOnce());
    expect(String(assign.mock.calls[0]?.[0])).toContain('/api/v1/reports/students/export/?');
    expect(String(assign.mock.calls[0]?.[0])).toContain('search=ra');
    expect(String(assign.mock.calls[0]?.[0])).toContain('as=csv');
    expect(queueExport).not.toHaveBeenCalled();
  });

  it('queues a large list and says a notification will follow', async () => {
    queueExport.mockResolvedValue({ id: 'job-1' });
    render(<ExportMenu reportKey="students" count={INLINE_EXPORT_LIMIT + 1} />);
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /excel/i }));
    await waitFor(() =>
      expect(queueExport).toHaveBeenCalledWith(
        expect.objectContaining({ report_key: 'students', format: 'xlsx' }),
      ),
    );
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Export queued' }));
  });

  it('renders nothing without the export right', () => {
    canMock.value = false;
    const { container } = render(<ExportMenu reportKey="students" count={1} />);
    expect(container).toBeEmptyDOMElement();
    canMock.value = true;
  });
});
