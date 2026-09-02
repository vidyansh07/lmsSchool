'use client';

import { useRef, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { removeProfileImage, uploadProfileImage } from '@/lib/auth';

/**
 * Profile image upload.
 *
 * The `accept` attribute and the size check here are conveniences that give
 * fast feedback. The real validation — content inspection, re-encoding, safe
 * naming — happens on the server, which does not trust any of this.
 */
const MAX_CLIENT_BYTES = 2 * 1024 * 1024;

export function ProfileImageField() {
  const { user, setUser } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState('');
  const [isBusy, setIsBusy] = useState(false);

  async function onSelect(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError('');
    if (file.size > MAX_CLIENT_BYTES) {
      setError('Image must be 2 MB or smaller.');
      if (inputRef.current) inputRef.current.value = '';
      return;
    }

    setIsBusy(true);
    try {
      setUser(await uploadProfileImage(file));
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'The image could not be uploaded.',
      );
    } finally {
      setIsBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  async function onRemove() {
    setIsBusy(true);
    setError('');
    try {
      setUser(await removeProfileImage());
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The image could not be removed.');
    } finally {
      setIsBusy(false);
    }
  }

  const initials = (user?.full_name || user?.email || '?').slice(0, 1).toUpperCase();

  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="flex size-16 items-center justify-center overflow-hidden rounded-full border border-border bg-muted">
        {user?.profile_image_url ? (
          /* The image is served by an authenticated API route, so Next's image
             optimiser cannot fetch it; a plain <img> is correct here. */
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={user.profile_image_url}
            alt=""
            className="size-full object-cover"
            width={64}
            height={64}
          />
        ) : (
          <span aria-hidden="true" className="text-xl font-medium text-muted-foreground">
            {initials}
          </span>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isBusy}
            onClick={() => inputRef.current?.click()}
          >
            {user?.profile_image_url ? 'Replace photo' : 'Upload photo'}
          </Button>
          {user?.profile_image_url ? (
            <Button type="button" variant="ghost" size="sm" disabled={isBusy} onClick={onRemove}>
              Remove
            </Button>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">JPEG, PNG or WEBP. Up to 2 MB.</p>
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
        aria-label="Profile photo"
        onChange={onSelect}
      />
    </div>
  );
}
