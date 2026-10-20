/**
 * `/activities/<id>` and `/dsr/<id>` are the links notifications carry. They
 * had no route, so "Open" was a 404; they now forward to where the record is
 * actually read, by what the reader may do.
 */
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ActivityLinkForward } from '@/app/activities/[activityId]/page';
import { DsrLinkForward } from '@/app/dsr/[dsrId]/page';

const replace = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));
const getDsr = vi.hoisted(() => vi.fn());
vi.mock('@/lib/dsr', () => ({ getDsr }));

function signedIn(role: string, capabilities: string[] = []) {
  useAuth.mockReturnValue({
    user: { id: 'u1', role, capabilities },
    isLoading: false,
    can: (capability: string) => capabilities.includes(capability),
  });
}

async function renderWith(element: React.ReactElement) {
  render(element);
}

beforeEach(() => {
  replace.mockReset();
  getDsr.mockReset();
});

describe('notification link routes', () => {
  it('opens an activity in the staff drawer for someone who reads activities', async () => {
    signedIn('manager', ['activity.view_any']);
    await renderWith(<ActivityLinkForward activityId="act-1" />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/activities?activity=act-1'));
  });

  it("sends a student to their own activities instead of a staff screen", async () => {
    signedIn('student');
    await renderWith(<ActivityLinkForward activityId="act-1" />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-activities?activity=act-1'));
  });

  it('opens a report in the review sheet for a reviewer', async () => {
    signedIn('manager', ['dsr.view_any']);
    await renderWith(<DsrLinkForward dsrId="dsr-1" />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dsr?report=dsr-1'));
    expect(getDsr).not.toHaveBeenCalled();
  });

  it('takes the trainer to the class itself, where a turned-back report is corrected', async () => {
    signedIn('trainer');
    getDsr.mockResolvedValue({ id: 'dsr-1', session: 'session-9' });
    await renderWith(<DsrLinkForward dsrId="dsr-1" />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/teaching/today?session=session-9'));
  });
});
