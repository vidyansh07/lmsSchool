import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Toaster, ToastProvider, useToast } from '@/components/ui/toast';

function Harness() {
  const { toast, dismiss } = useToast();
  return (
    <div>
      <button onClick={() => toast({ title: 'Batch created', description: 'GRS-B-004 is ready.' })}>
        Notify success
      </button>
      <button onClick={() => toast({ title: 'Export failed', variant: 'error', durationMs: 0 })}>
        Notify error
      </button>
      <button
        onClick={() => {
          const id = toast({ title: 'Quick', durationMs: 0 });
          dismiss(id);
        }}
      >
        Notify and immediately dismiss
      </button>
      <Toaster />
    </div>
  );
}

function renderHarness() {
  return render(
    <ToastProvider>
      <Harness />
    </ToastProvider>,
  );
}

describe('Toast', () => {
  it('useToast throws a clear error outside <ToastProvider>', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    function Lonely() {
      useToast();
      return null;
    }
    expect(() => render(<Lonely />)).toThrow(/must be used inside <ToastProvider>/);
    spy.mockRestore();
  });

  it('Toaster throws a clear error outside <ToastProvider>', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Toaster />)).toThrow(/must be used inside <ToastProvider>/);
    spy.mockRestore();
  });

  it('announces new toasts in a single polite live region', () => {
    const { container } = renderHarness();
    const regions = container.querySelectorAll('[aria-live]');
    expect(regions).toHaveLength(1);
    expect(regions[0]).toHaveAttribute('aria-live', 'polite');
  });

  it('shows a toast with its title and description', async () => {
    const user = userEvent.setup();
    renderHarness();

    await user.click(screen.getByRole('button', { name: 'Notify success' }));
    expect(screen.getByText('Batch created')).toBeInTheDocument();
    expect(screen.getByText('GRS-B-004 is ready.')).toBeInTheDocument();
  });

  it('stacks multiple toasts at once', async () => {
    const user = userEvent.setup();
    renderHarness();

    await user.click(screen.getByRole('button', { name: 'Notify success' }));
    await user.click(screen.getByRole('button', { name: 'Notify error' }));
    expect(screen.getByText('Batch created')).toBeInTheDocument();
    expect(screen.getByText('Export failed')).toBeInTheDocument();
  });

  it('dismisses via its own close button', async () => {
    const user = userEvent.setup();
    renderHarness();

    await user.click(screen.getByRole('button', { name: 'Notify error' }));
    expect(screen.getByText('Export failed')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Dismiss notification' }));
    await waitFor(() => expect(screen.queryByText('Export failed')).not.toBeInTheDocument());
  });

  it('auto-dismisses after its duration elapses', async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <AutoDismissHarness />
      </ToastProvider>,
    );
    await user.click(screen.getByRole('button', { name: 'Notify' }));
    expect(screen.getByText('Fleeting')).toBeInTheDocument();

    await waitFor(() => expect(screen.queryByText('Fleeting')).not.toBeInTheDocument(), { timeout: 1000 });
  });

  it('does not auto-dismiss when durationMs is 0', async () => {
    const user = userEvent.setup();
    renderHarness();

    await user.click(screen.getByRole('button', { name: 'Notify error' }));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(screen.getByText('Export failed')).toBeInTheDocument();
  });

  it('can be dismissed programmatically by the id toast() returns', async () => {
    const user = userEvent.setup();
    renderHarness();

    await user.click(screen.getByRole('button', { name: 'Notify and immediately dismiss' }));
    await waitFor(() => expect(screen.queryByText('Quick')).not.toBeInTheDocument());
  });
});

function AutoDismissHarness() {
  const { toast } = useToast();
  return (
    <div>
      <button onClick={() => toast({ title: 'Fleeting', durationMs: 60 })}>Notify</button>
      <Toaster />
    </div>
  );
}
