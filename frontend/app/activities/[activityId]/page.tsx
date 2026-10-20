'use client';

/**
 * Where an activity notification's "Open" lands (`/activities/<id>`, written
 * by `apps/work/services.py`). There is no separate detail screen: staff read
 * an activity in the drawer on `/activities`, and a student reads the ones
 * shared with them on `/my-activities`. This page only forwards, so the links
 * already sitting in people's notification lists keep working.
 */

import { useRouter } from 'next/navigation';
import { use, useEffect } from 'react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { LoadingState } from '@/components/states';
import { Capability } from '@/lib/capabilities';

export function ActivityLinkForward({ activityId }: { activityId: string }) {
  const router = useRouter();
  const { user, can } = useAuth();

  useEffect(() => {
    if (!user) return;
    const query = `?activity=${encodeURIComponent(activityId)}`;
    const staff = can(Capability.activityViewAny) || user.role === 'trainer';
    router.replace(user.role === 'student' || !staff ? `/my-activities${query}` : `/activities${query}`);
  }, [user, can, router, activityId]);

  return <LoadingState label="Opening the activity…" rows={3} />;
}

export default function ActivityLinkPage({ params }: { params: Promise<{ activityId: string }> }) {
  const { activityId } = use(params);
  return (
    <RequireAuth>
      <ActivityLinkForward activityId={activityId} />
    </RequireAuth>
  );
}
