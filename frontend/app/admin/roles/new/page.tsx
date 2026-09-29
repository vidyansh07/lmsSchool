import { RequireAuth } from "@/components/require-auth";
import { Capability } from "@/lib/capabilities";
import { RoleBuilder } from "@/components/roles/role-builder";

export default function NewRolePage() {
  return (
    <RequireAuth capability={Capability.roleManage}>
      <RoleBuilder />
    </RequireAuth>
  );
}
