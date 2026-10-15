import { describe, expect, it, vi } from 'vitest';

import AdminTrainersPage from '@/app/admin/trainers/page';

const redirect = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ redirect }));

describe('legacy admin trainers route', () => {
  it('redirects to the canonical trainer hub', () => {
    AdminTrainersPage();
    expect(redirect).toHaveBeenCalledWith('/manage/trainers');
  });
});
