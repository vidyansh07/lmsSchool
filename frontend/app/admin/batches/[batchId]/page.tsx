import { RequireAuth } from '@/components/require-auth';
import { BatchDetailView } from './batch-detail-view';

// Not a client component: reading the route param needs nothing that only a
// browser can do, so it stays a server component and ships no JavaScript of
// its own. The interactive detail view — the part that actually needs
// `useState`/`useEffect` — is the client boundary, kept in its own file.
export default async function AdminBatchPage({
  params,
}: {
  params: Promise<{ batchId: string }>;
}) {
  const { batchId } = await params;
  return (
    <RequireAuth>
      <BatchDetailView batchId={batchId} />
    </RequireAuth>
  );
}

// Re-exported so existing tests can keep importing it from the page module.
export { RosterPanel } from './batch-detail-view';
