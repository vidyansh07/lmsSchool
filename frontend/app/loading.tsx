import { LoadingState } from '@/components/states';

/** Route-level loading UI, streamed by Next while a segment resolves. */
export default function Loading() {
  return <LoadingState label="Loading page…" rows={4} />;
}
