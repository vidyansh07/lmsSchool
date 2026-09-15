import Link from "next/link";

import { RequireAuth } from "@/components/require-auth";
import { PermissionMatrix } from "@/components/roles/permission-matrix";

export default function MatrixPage() {
  return (
    <RequireAuth>
      <div className="animate-rise-in space-y-6">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            Permission matrix
          </h1>
          <p className="text-sm text-muted-foreground">
            Every role by every permission. Change a role from{" "}
            <Link href="/admin/roles" className="underline underline-offset-2">
              Roles
            </Link>
            .
          </p>
        </div>
        <PermissionMatrix />
      </div>
    </RequireAuth>
  );
}
