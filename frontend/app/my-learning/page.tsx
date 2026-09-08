'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/academic-labels';
import {
  learningHome,
  listBookmarks,
  listClassmates,
  listNotes,
  upcomingWork,
} from '@/lib/communication';
import type { Bookmark, LearningHome, LessonNote, Peer, UpcomingItem } from '@/types/api';

const KIND_LABEL: Record<string, string> = {
  assignment_due: 'Assignment',
  project_due: 'Project',
  quiz: 'Weekly test',
  exam: 'Examination',
};

/** Where to pick up, what is coming, and the student's own working material. */
function MyLearning() {
  const [home, setHome] = useState<LearningHome[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingItem[]>([]);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [notes, setNotes] = useState<LessonNote[]>([]);
  const [classmates, setClassmates] = useState<Record<string, Peer[]>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([learningHome(), upcomingWork(), listBookmarks(), listNotes()])
      .then(async ([rows, due, marks, written]) => {
        if (cancelled) return;
        setHome(rows);
        setUpcoming(due);
        setBookmarks(marks);
        setNotes(written);

        // The class list is configurable, so a refusal is expected rather than
        // an error: an institution may simply not share it.
        const peers = await Promise.all(
          rows.map((row) =>
            listClassmates(row.enrollment_id)
              .then((list) => [row.enrollment_id, list] as const)
              .catch(() => null),
          ),
        );
        if (cancelled) return;
        setClassmates(
          Object.fromEntries(peers.filter((entry): entry is [string, Peer[]] => entry !== null)),
        );
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading) return <LoadingState label="Loading your learning…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your learning"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="stagger space-y-6">
      <div className="animate-rise-in space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My learning</h1>
        <p className="text-sm text-muted-foreground">
          Where you left off, what is coming, and everything you have saved.
        </p>
      </div>

      {home.length === 0 ? (
        <EmptyState
          title="Nothing yet"
          description="This fills up once you are enrolled and have opened a lesson."
        />
      ) : (
        home.map((row) => (
          <Card key={row.enrollment_id} data-testid="learning-card" className="animate-rise-in">
            <CardHeader className="gap-1">
              <span className="font-mono text-xs text-muted-foreground">{row.batch_code}</span>
              <CardTitle>{row.course_title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {row.continue_learning ? (
                <div>
                  <p className="text-sm text-muted-foreground">Continue where you left off</p>
                  <Button asChild size="sm" className="mt-1" data-testid="continue-learning">
                    <Link
                      href={`/courses/${row.continue_learning.course_slug}/learn/${row.continue_learning.lesson_id}`}
                    >
                      {row.continue_learning.lesson_title}
                    </Link>
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Nothing left to continue on this course.
                </p>
              )}

              {row.recent.length > 0 ? (
                <div>
                  <p className="text-sm font-medium">Recently opened</p>
                  <ul className="mt-1 space-y-1 text-sm">
                    {row.recent.map((lesson) => (
                      <li key={lesson.lesson_id}>
                        <Link
                          className="underline hover:text-foreground"
                          href={`/courses/${lesson.course_slug}/learn/${lesson.lesson_id}`}
                        >
                          {lesson.lesson_title}
                        </Link>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {formatDateTime(lesson.last_accessed_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {classmates[row.enrollment_id] ? (
                <div>
                  <p className="text-sm font-medium">
                    On this batch ({classmates[row.enrollment_id]?.length})
                  </p>
                  <ul className="mt-1 flex flex-wrap gap-2" data-testid="classmates">
                    {classmates[row.enrollment_id]?.map((peer) => (
                      <li key={peer.student_code}>
                        <Badge variant={peer.is_you ? 'success' : 'neutral'}>
                          {peer.full_name}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </CardContent>
          </Card>
        ))
      )}

      <Card className="animate-rise-in">
        <CardHeader>
          <CardTitle>Coming up</CardTitle>
          <CardDescription>The next two weeks, from your calendar.</CardDescription>
        </CardHeader>
        <CardContent>
          {upcoming.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing due in the next two weeks.</p>
          ) : (
            <ul className="space-y-2" data-testid="upcoming">
              {upcoming.map((item) => (
                <li key={`${item.kind}-${item.title}-${item.start}`} className="text-sm">
                  <Badge variant="neutral">{KIND_LABEL[item.kind] ?? item.kind}</Badge>
                  <span className="ml-2 font-medium">{item.title}</span>
                  <span className="ml-2 text-muted-foreground">
                    {formatDateTime(item.start)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="stagger grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>Bookmarks</CardTitle>
          </CardHeader>
          <CardContent>
            {bookmarks.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Bookmark a lesson from the course player to find it here.
              </p>
            ) : (
              <ul className="space-y-2 text-sm">
                {bookmarks.map((item) => (
                  <li key={item.id}>
                    <Link
                      className="underline hover:text-foreground"
                      href={`/courses/${item.course_slug}/learn/${item.lesson}`}
                    >
                      {item.lesson_title}
                    </Link>
                    {item.note ? (
                      <p className="text-xs text-muted-foreground">{item.note}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="animate-rise-in">
          <CardHeader>
            <CardTitle>My notes</CardTitle>
          </CardHeader>
          <CardContent>
            {notes.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Notes you write on a lesson appear here.
              </p>
            ) : (
              <ul className="space-y-2 text-sm">
                {notes.map((item) => (
                  <li key={item.id}>
                    <Link
                      className="underline hover:text-foreground"
                      href={`/courses/${item.course_slug}/learn/${item.lesson}`}
                    >
                      {item.lesson_title}
                    </Link>
                    <p className="whitespace-pre-wrap text-xs text-muted-foreground">
                      {item.body}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function MyLearningPage() {
  return (
    <RequireAuth>
      <MyLearning />
    </RequireAuth>
  );
}
