/**
 * Bookmarks and lesson notes.
 *
 * `/my-learning` has always advertised both — "Bookmark a lesson from the course
 * player to find it here", "Notes you write on a lesson appear here" — and the
 * endpoints and their API clients have existed just as long. Nothing ever called
 * them: the player, the one screen that could, offered only "Mark as complete",
 * so neither panel on `/my-learning` was reachable from the interface.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LessonAside } from '@/components/lesson-aside';
import { ApiError } from '@/lib/api';

const listBookmarks = vi.hoisted(() => vi.fn());
const getNote = vi.hoisted(() => vi.fn());
const setBookmark = vi.hoisted(() => vi.fn());
const removeBookmark = vi.hoisted(() => vi.fn());
const saveNote = vi.hoisted(() => vi.fn());
vi.mock('@/lib/communication', () => ({
  listBookmarks,
  getNote,
  setBookmark,
  removeBookmark,
  saveNote,
}));

beforeEach(() => {
  vi.clearAllMocks();
  listBookmarks.mockResolvedValue([]);
  // An absent note is an empty object, not a 404.
  getNote.mockResolvedValue({});
  setBookmark.mockResolvedValue({});
  removeBookmark.mockResolvedValue(undefined);
  saveNote.mockResolvedValue({});
});

describe('the bookmark control', () => {
  it('creates a bookmark for the lesson being read', async () => {
    render(<LessonAside lessonId="lesson-1" />);

    const button = await screen.findByTestId('lesson-bookmark');
    expect(button).toHaveTextContent('Bookmark this lesson');
    fireEvent.click(button);

    await waitFor(() => expect(setBookmark).toHaveBeenCalledWith('lesson-1'));
    expect(await screen.findByText(/bookmarked/i)).toBeInTheDocument();
  });

  it('offers to remove a bookmark this lesson already has', async () => {
    listBookmarks.mockResolvedValue([{ id: 'bm-1', lesson: 'lesson-1', note: '' }]);
    render(<LessonAside lessonId="lesson-1" />);

    const button = await screen.findByRole('button', { name: /remove bookmark/i });
    fireEvent.click(button);
    await waitFor(() => expect(removeBookmark).toHaveBeenCalledWith('lesson-1'));
  });

  it('says so when the bookmark could not be saved', async () => {
    setBookmark.mockRejectedValue(
      new ApiError(403, 'permission_denied', 'You are not enrolled on this course.', 'req-1'),
    );
    render(<LessonAside lessonId="lesson-1" />);

    fireEvent.click(await screen.findByTestId('lesson-bookmark'));
    expect(await screen.findByText(/not enrolled on this course/i)).toBeInTheDocument();
  });
});

describe('the lesson note', () => {
  it('shows the note already written and cannot be saved unchanged', async () => {
    getNote.mockResolvedValue({ id: 'n-1', lesson: 'lesson-1', body: 'Rollback first.' });
    render(<LessonAside lessonId="lesson-1" />);

    await waitFor(() => expect(screen.getByLabelText('Note')).toHaveValue('Rollback first.'));
    expect(screen.getByTestId('lesson-note-save')).toBeDisabled();
  });

  it('writes what was typed', async () => {
    render(<LessonAside lessonId="lesson-1" />);

    const field = await screen.findByLabelText('Note');
    fireEvent.change(field, { target: { value: 'Health checks on every service.' } });
    fireEvent.click(screen.getByTestId('lesson-note-save'));

    await waitFor(() =>
      expect(saveNote).toHaveBeenCalledWith('lesson-1', 'Health checks on every service.'),
    );
    expect(await screen.findByText('Note saved.')).toBeInTheDocument();
  });

  it('says a cleared note was cleared, because writing nothing deletes it', async () => {
    getNote.mockResolvedValue({ id: 'n-1', lesson: 'lesson-1', body: 'Old note.' });
    render(<LessonAside lessonId="lesson-1" />);

    const field = await screen.findByLabelText('Note');
    await waitFor(() => expect(field).toHaveValue('Old note.'));
    fireEvent.change(field, { target: { value: '' } });
    fireEvent.click(screen.getByTestId('lesson-note-save'));

    await waitFor(() => expect(saveNote).toHaveBeenCalledWith('lesson-1', ''));
    expect(await screen.findByText('Note cleared.')).toBeInTheDocument();
  });
});
