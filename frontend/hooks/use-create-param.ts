'use client';

import { useSearchParams } from 'next/navigation';
import { useCallback, useState } from 'react';

/**
 * `?create=1` opens a screen's "add" dialog straight away — where a command
 * palette quick action ("Add a trainer") lands. Only when the person may
 * create (the button would be there anyway); closing the dialog takes the
 * parameter back out of the address so a refresh does not reopen it.
 */
export function useCreateParam(allowed: boolean): [boolean, (open: boolean) => void] {
  const searchParams = useSearchParams();
  const [open, setOpenState] = useState(() => allowed && searchParams?.get('create') === '1');

  const setOpen = useCallback((next: boolean) => {
    setOpenState(next);
    if (!next && typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if (params.has('create')) {
        params.delete('create');
        const search = params.toString();
        window.history.replaceState(
          window.history.state,
          '',
          `${window.location.pathname}${search ? `?${search}` : ''}${window.location.hash}`,
        );
      }
    }
  }, []);

  return [open, setOpen];
}
