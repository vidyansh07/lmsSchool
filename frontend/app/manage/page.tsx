/**
 * `/manage` on its own names a section, not a screen — the brief is two hubs,
 * batches and trainers, and a manager's own workday starts with cohorts far
 * more often than with the trainer roster. Redirecting straight to the
 * batches hub means a bookmark or a nav link to "Manage" always lands
 * somewhere real rather than on a page whose only content is "pick one".
 */
import { redirect } from 'next/navigation';

export default function ManagePage() {
  redirect('/manage/batches');
}
