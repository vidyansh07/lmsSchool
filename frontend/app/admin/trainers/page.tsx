import { redirect } from 'next/navigation';

/**
 * Backwards-compatible entry point. Trainer operations now have one canonical
 * hub for administrators and managers, so old bookmarks land there too.
 */
export default function AdminTrainersPage() {
  redirect('/manage/trainers');
}
