'use client';

import { useEffect, useState } from 'react';
import { Download, ExternalLink, FileText, Link2 } from 'lucide-react';

import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { getVideoPlayback } from '@/lib/courses';
import { formatBytes } from '@/lib/course-labels';
import type { LessonContent, LessonResource, VideoPlayback } from '@/types/api';

/**
 * Video player.
 *
 * The playback URL is fetched on demand from its own endpoint rather than read
 * from the lesson payload, because the server only hands it out after checking
 * entitlement. Providers other than external URL need a signed URL from their
 * own API; until that integration exists they render an honest placeholder
 * instead of a broken player.
 */
interface PlaybackState {
  playback: VideoPlayback | null;
  error: ApiError | null;
  isLoading: boolean;
  lessonId: string;
}

function VideoPanel({ lessonId }: { lessonId: string }) {
  const [state, setState] = useState<PlaybackState>({
    playback: null,
    error: null,
    isLoading: true,
    lessonId,
  });

  // Reset during render when the lesson changes, rather than with a synchronous
  // setState inside the effect, which would cascade a render.
  if (state.lessonId !== lessonId) {
    setState({ playback: null, error: null, isLoading: true, lessonId });
  }

  useEffect(() => {
    let cancelled = false;

    getVideoPlayback(lessonId)
      .then((result) => {
        if (!cancelled) {
          setState({ playback: result, error: null, isLoading: false, lessonId });
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            playback: null,
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
            lessonId,
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [lessonId]);

  const { playback, error, isLoading } = state;

  if (isLoading) return <LoadingState label="Loading video…" rows={2} />;
  if (error) {
    return (
      <ErrorState
        title="Video unavailable"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  if (!playback?.playback_url) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-[var(--radius-card)] border border-dashed border-border bg-muted text-center">
        <div className="space-y-1 px-6">
          <p className="text-sm font-medium">Video player</p>
          <p className="text-xs text-muted-foreground">
            {playback?.provider && playback.provider !== 'external_url'
              ? `Hosted on ${playback.provider}. Signed playback is not wired up yet.`
              : 'No playable source is configured for this lesson.'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <video
      key={playback.playback_url}
      controls
      preload="metadata"
      controlsList="nodownload"
      className="aspect-video w-full rounded-[var(--radius-card)] border border-border bg-black"
    >
      <source src={playback.playback_url} />
      Your browser cannot play this video.
    </video>
  );
}

function ResourceRow({ resource }: { resource: LessonResource }) {
  const isLink = resource.kind === 'link';
  return (
    <li className="flex flex-wrap items-center gap-3 border-b border-border py-2.5 last:border-b-0">
      {isLink ? (
        <Link2 className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      ) : (
        <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{resource.title}</p>
        {resource.description ? (
          <p className="truncate text-xs text-muted-foreground">{resource.description}</p>
        ) : null}
      </div>
      {!isLink && resource.size_bytes ? (
        <span className="text-xs text-muted-foreground">{formatBytes(resource.size_bytes)}</span>
      ) : null}
      {isLink ? (
        <Button asChild variant="outline" size="sm">
          {/* noopener/noreferrer: the destination is author-supplied. */}
          <a href={resource.external_url} target="_blank" rel="noopener noreferrer">
            Open
            <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
        </Button>
      ) : resource.download_url ? (
        <Button asChild variant="outline" size="sm">
          <a href={resource.download_url}>
            Download
            <Download className="size-3.5" aria-hidden="true" />
          </a>
        </Button>
      ) : (
        <Badge>Not downloadable</Badge>
      )}
    </li>
  );
}

/**
 * Render one lesson's body, whatever its content type.
 *
 * Adding a content type means adding a branch here and nowhere else in the
 * interface — the summary, navigation and access rules are all type-agnostic.
 */
export function LessonBody({ lesson }: { lesson: LessonContent }) {
  return (
    <div className="space-y-6">
      {lesson.content_type === 'video' ? <VideoPanel lessonId={lesson.id} /> : null}

      {lesson.content_type === 'text' && lesson.text_content ? (
        // Rendered as plain text, never as HTML: author content is not trusted
        // markup, and `whitespace-pre-line` preserves the intended layout.
        <div className="max-w-prose whitespace-pre-line text-sm leading-relaxed">
          {lesson.text_content}
        </div>
      ) : null}

      {lesson.content_type === 'external_link' && lesson.external_url ? (
        <Alert variant="info" className="space-y-3">
          <p>This lesson links to material hosted elsewhere.</p>
          <Button asChild size="sm">
            <a href={lesson.external_url} target="_blank" rel="noopener noreferrer">
              Open the resource
              <ExternalLink className="size-3.5" aria-hidden="true" />
            </a>
          </Button>
        </Alert>
      ) : null}

      {lesson.content_type === 'document' && lesson.resources.length === 0 ? (
        <Alert variant="warning">This document lesson has no attached file yet.</Alert>
      ) : null}

      {lesson.description ? (
        <p className="max-w-prose text-sm text-muted-foreground">{lesson.description}</p>
      ) : null}

      {lesson.resources.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Resources</CardTitle>
          </CardHeader>
          <CardContent>
            <ul>
              {lesson.resources.map((resource) => (
                <ResourceRow key={resource.id} resource={resource} />
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
