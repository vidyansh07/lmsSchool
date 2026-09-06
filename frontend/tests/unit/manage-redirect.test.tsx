import { describe, expect, it, vi } from 'vitest';

const redirect = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ redirect }));

describe('ManagePage', () => {
  it('sends /manage straight to the batches hub', async () => {
    const { default: ManagePage } = await import('@/app/manage/page');
    ManagePage();
    expect(redirect).toHaveBeenCalledWith('/manage/batches');
  });
});
