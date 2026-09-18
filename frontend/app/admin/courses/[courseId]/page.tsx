import { RequireAuth } from '@/components/require-auth';
import { CourseEditor } from './course-editor';

// Not a client component: reading the route param needs nothing that only a
// browser can do, so it stays a server component and ships no JavaScript of
// its own. The interactive editor — the part that actually needs
// `useState`/`useEffect` — is the client boundary, kept in its own file.
export default async function AdminCoursePage({
  params,
}: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = await params;
  return (
    <RequireAuth>
      <CourseEditor courseId={courseId} />
    </RequireAuth>
  );
}

// Re-exported so existing tests can keep importing it from the page module.
export { ModulePanel } from './course-editor';
