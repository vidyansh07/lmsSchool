import { Suspense } from "react";

import { RequireAuth } from "@/components/require-auth";
import { RequirementsBoard } from "@/components/requirements/requirements-board";
import { LoadingState } from "@/components/states";

export default function RequirementsPage() {
  return (
    <RequireAuth>
      <Suspense
        fallback={<LoadingState label="Loading requirements…" rows={3} />}
      >
        <RequirementsBoard />
      </Suspense>
    </RequireAuth>
  );
}
