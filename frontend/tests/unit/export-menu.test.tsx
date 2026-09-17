/**
 * The Export menu: four formats (Excel, PDF, CSV, Print); choosing one first
 * shows a confirmation dialog with the server's real row count and only
 * then downloads, queues, or opens the print page; nothing for somebody
 * without the export right.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ExportMenu, INLINE_EXPORT_LIMIT } from '@/components/export-menu';

const queueExport = vi.hoisted(() => vi.fn());
const getReportCount = vi.hoisted(() => vi.fn());
const toast = vi.hoisted(() => vi.fn());
const canMock = vi.hoisted(() => ({ value: true }));

vi.mock('@/lib/reporting', async () => {
  const actual = await vi.importActual<typeof import('@/lib/reporting')>('@/lib/reporting');
  return { ...actual, queueExport, getReportCount };
});
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ toast }) }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => ({ can: () => canMock.value }) }));

describe('ExportMenu', () => {
  afterEach(() => {
    queueExport.mockReset();
    getReportCount.mockReset();
    toast.mockReset();
  });

  it('offers Excel, PDF, CSV and Print', async () => {
    getReportCount.mockResolvedValue(12);
    render(<ExportMenu reportKey="students" filters={{ search: 'ra' }} count={12} />);
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    expect(await screen.findByRole('menuitem', { name: /excel/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /pdf/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /csv/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /print/i })).toBeInTheDocument();
  });

  it('asks the server for the count, confirms with the real number, and only then downloads', async () => {
    const assign = vi.fn();
    Object.defineProperty(window, 'location', { value: { assign }, writable: true });
    getReportCount.mockResolvedValue(1204);
    render(<ExportMenu reportKey="students" filters={{ search: 'ra' }} count={12} />);
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /csv/i }));

    // Blocked until the count comes back and is shown.
    expect(assign).not.toHaveBeenCalled();
    const confirmDialog = await screen.findByTestId('export-count-confirm');
    expect(confirmDialog).toHaveTextContent('1,204');
    expect(confirmDialog).toHaveTextContent('CSV');
    expect(getReportCount).toHaveBeenCalledWith('students', expect.objectContaining({ search: 'ra' }));

    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^export$/i }));
    await waitFor(() => expect(assign).toHaveBeenCalledOnce());
    expect(String(assign.mock.calls[0]?.[0])).toContain('/api/v1/reports/students/export/?');
    expect(String(assign.mock.calls[0]?.[0])).toContain('as=csv');
    expect(queueExport).not.toHaveBeenCalled();
  });

  it('queues a large list after confirming, per the server-resolved count', async () => {
    getReportCount.mockResolvedValue(INLINE_EXPORT_LIMIT + 1);
    queueExport.mockResolvedValue({ id: 'job-1' });
    render(<ExportMenu reportKey="students" count={5} />);
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /excel/i }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /^export$/i }));
    await waitFor(() =>
      expect(queueExport).toHaveBeenCalledWith(
        expect.objectContaining({ report_key: 'students', format: 'xlsx' }),
      ),
    );
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Export queued' }));
  });

  it('cancelling the confirmation exports nothing', async () => {
    getReportCount.mockResolvedValue(3);
    render(<ExportMenu reportKey="students" count={3} />);
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /csv/i }));
    await screen.findByTestId('export-count-confirm');
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByTestId('export-count-confirm')).not.toBeInTheDocument());
    expect(queueExport).not.toHaveBeenCalled();
  });

  it('shows a count error with a retry, and never queues from it', async () => {
    getReportCount.mockRejectedValueOnce(new Error('boom'));
    render(<ExportMenu reportKey="students" count={3} />);
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /csv/i }));
    expect(await screen.findByTestId('export-count-error')).toBeInTheDocument();
    expect(queueExport).not.toHaveBeenCalled();

    getReportCount.mockResolvedValueOnce(3);
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByTestId('export-count-confirm')).toHaveTextContent('3');
  });

  it('print opens the returned HTML in a new tab instead of downloading a file', async () => {
    getReportCount.mockResolvedValue(7);
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(<ExportMenu reportKey="students" count={7} />);
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /print/i }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /^print$/i }));
    await waitFor(() => expect(open).toHaveBeenCalledOnce());
    expect(String(open.mock.calls[0]?.[0])).toContain('as=print');
    expect(open.mock.calls[0]?.[2]).toContain('noopener');
    open.mockRestore();
  });

  it('renders nothing without the export right', () => {
    canMock.value = false;
    const { container } = render(<ExportMenu reportKey="students" count={1} />);
    expect(container).toBeEmptyDOMElement();
    canMock.value = true;
  });
});
