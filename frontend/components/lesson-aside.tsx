'use client';

import { useEffect, useState } from 'react';
import { Bookmark, BookmarkCheck } from 'lucide-react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/input';
import { errorMessage } from '@/lib/api';
import {
  getNote,
  listBookmarks,
  removeBookmark,
  saveNote,
  setBookmark,
} from '@/lib/communication';
import type { LessonNote } from '@/types/api';

/**
 * The bookmark and the note for the lesson being read.
 *
 * Both endpoints and both API clients have existed since the learning surface
 * was built, and `/my-learning` has always advertised them -- "Bookmark a
 * lesson from the course player to find it here", "Notes you write on a lesson
 * appear here". Nothing ever called them: the player was the one screen that
 * could, and it only ever offered "Mark as complete". So the two panels on
 * `/my-learning` could not be filled by any route through the interface.
 *
 * Read on mount rather than handed down from the player, because the lesson
 * payload carries neither: the bookmark list and the note are their own
 * requests, scoped to the caller's enrolment by the server.
 *
 * A failure here never blocks the lesson. The lesson body is what the student
 * came for; a bookmark that could not be saved says so in its own panel and
 * leaves the rest of the screen alone.
 */
export function LessonAside({ lessonId }: { lessonId: string }) {
  const [bookmarked, setBookmarked] = useState(false);
  const [note, setNote] = useState('');
  const [savedNote, setSavedNote] = useState('');
  const [problem, setProblem] = useState('');
  const [notice, setNotice] = useState('');
  const [isBusy, setIsBusy] = useState(false);

  // Reset during render when the student moves on: this component is reused
  // across lessons, and the previous lesson's note in the box would be written
  // to the new lesson the moment they pressed Save.
  const [seen, setSeen] = useState(lessonId);
  if (seen !== lessonId) {
    setSeen(lessonId);
    setBookmarked(false);
    setNote('');
    setSavedNote('');
    setProblem('');
    setNotice('');
  }

  useEffect(() => {
    let cancelled = false;

    Promise.all([listBookmarks(), getNote(lessonId)])
      .then(([marks, existing]) => {
        if (cancelled) return;
        setBookmarked(marks.some((mark) => mark.lesson === lessonId));
        // An absent note is `{}`, not a 404: the endpoint answers "nothing
        // written yet" with an empty object.
        const body = (existing as LessonNote).body ?? '';
        setNote(body);
        setSavedNote(body);
      })
      .catch(() => {
        // Silent: nothing is lost, and an error banner over an empty panel on
        // first paint is noise. A failed *write* is what a student needs told.
      });

    return () => {
      cancelled = true;
    };
  }, [lessonId]);

  async function toggleBookmark() {
    setIsBusy(true);
    setProblem('');
    setNotice('');
    try {
      if (bookmarked) {
        await removeBookmark(lessonId);
        setBookmarked(false);
        setNotice('Bookmark removed.');
      } else {
        await setBookmark(lessonId);
        setBookmarked(true);
        setNotice('Bookmarked. It is on your learning home.');
      }
    } catch (cause) {
      setProblem(errorMessage(cause, 'That bookmark could not be saved.'));
    } finally {
      setIsBusy(false);
    }
  }

  async function keepNote() {
    setIsBusy(true);
    setProblem('');
    setNotice('');
    try {
      await saveNote(lessonId, note);
      setSavedNote(note);
      // Writing nothing deletes the note, which `set_note` does deliberately;
      // say which of the two happened.
      setNotice(note.trim() ? 'Note saved.' : 'Note cleared.');
    } catch (cause) {
      setProblem(errorMessage(cause, 'That note could not be saved.'));
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <Card data-testid="lesson-aside">
      <CardHeader className="gap-1">
        <CardTitle as="h2" className="text-base">
          Your notes
        </CardTitle>
        <CardDescription>Private to you. Both appear on your learning home.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {problem ? <Alert variant="error">{problem}</Alert> : null}
        {notice ? (
          <Alert variant="success" role="status">
            {notice}
          </Alert>
        ) : null}

        <Button
          type="button"
          variant={bookmarked ? 'outline' : 'primary'}
          size="sm"
          disabled={isBusy}
          onClick={() => void toggleBookmark()}
          data-testid="lesson-bookmark"
        >
          {bookmarked ? (
            <BookmarkCheck className="size-4" aria-hidden="true" />
          ) : (
            <Bookmark className="size-4" aria-hidden="true" />
          )}
          {bookmarked ? 'Remove bookmark' : 'Bookmark this lesson'}
        </Button>

        <div className="space-y-1.5">
          <label htmlFor="lesson-note" className="block text-xs font-medium text-ink">
            Note
          </label>
          <Textarea
            id="lesson-note"
            rows={4}
            value={note}
            placeholder="What you want to remember about this lesson."
            onChange={(event) => setNote(event.target.value)}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isBusy || note === savedNote}
            onClick={() => void keepNote()}
            data-testid="lesson-note-save"
          >
            Save note
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
