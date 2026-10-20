/**
 * A chart whose data failed to load says so, with a retry, instead of drawing
 * its empty message — "Nothing is waiting on you" over a failed request reads
 * as a fact about the trainer's queue.
 */
import { fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ChartCard } from '@/components/ui/charts/chart-card';
import { useSection } from '@/hooks/use-section';

describe('ChartCard', () => {
  it('replaces the plot with the error and a retry when its data failed', () => {
    const onRetry = vi.fn();
    render(
      <ChartCard
        title="What is waiting on you"
        subtitle="Open work across your batches"
        error={{ message: 'The server did not answer.', requestId: 'req-1' }}
        onRetry={onRetry}
      >
        <p>Nothing is waiting on you</p>
      </ChartCard>,
    );
    expect(screen.queryByText('Nothing is waiting on you')).toBeNull();
    expect(screen.getByText('The server did not answer.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('draws the plot when there is no error', () => {
    render(
      <ChartCard title="Queue" subtitle="Open work">
        <p>Nothing is waiting on you</p>
      </ChartCard>,
    );
    expect(screen.getByText('Nothing is waiting on you')).toBeInTheDocument();
  });
});

describe('useSection', () => {
  it('never reports a failure as a null error', async () => {
    const { result } = renderHook(() =>
      useSection(() => Promise.reject(new TypeError('x is undefined')), [] as number[]),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).not.toBeNull();
    expect(result.current.error?.message).toBe('This section could not be loaded.');
  });
});
