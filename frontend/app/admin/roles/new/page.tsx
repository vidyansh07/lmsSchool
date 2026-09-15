import { RequireAuth } from "@/components/require-auth";
import { RoleBuilder } from "@/components/roles/role-builder";

export default function NewRolePage() {
  return (
    <RequireAuth>
      <RoleBuilder />
    </RequireAuth>
  );
}
