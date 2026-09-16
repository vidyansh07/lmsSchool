/**
 * Folded into the Student 360 page's Timeline tab (ERP Phase 11) — Phase
 * 10's own docstring on `StudentTimeline` called this exact move ("Phase 11
 * (Student 360) is expected to introduce the real tabbed student page and
 * fold this in as one of its tabs; nothing here needs to survive that move,
 * only the `StudentTimeline` component itself").
 *
 * A server-side redirect (`app/manage/page.tsx`'s pattern, not the
 * client-side one `app/manage/students/[enrollmentId]/page.tsx` needs):
 * everything this route needs — the id from the URL — is already in hand,
 * with no API call required first to learn where to go. Kept, rather than
 * deleted, so an old bookmark or link still lands somewhere real (D-128: no
 * dead links) instead of a 404.
 */
import { redirect } from 'next/navigation';

export default async function StudentTimelineRedirectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/students/${id}?tab=timeline`);
}
