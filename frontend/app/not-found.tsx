import Link from 'next/link';

import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="flex flex-col items-start gap-4 py-16">
      <p className="text-sm font-medium text-muted-foreground">404</p>
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="max-w-prose text-sm text-muted-foreground">
        The page you requested does not exist or has moved.
      </p>
      <Button asChild variant="outline">
        <Link href="/">Back to overview</Link>
      </Button>
    </div>
  );
}
