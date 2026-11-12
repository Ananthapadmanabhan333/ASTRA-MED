import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { AdminView } from "@/components/medical/admin-view";

export const metadata: Metadata = { title: "Users and audit log" };

export default function AdminPage() {
  return (
    <div className="space-y-5">
      <PageHeader title="Users and audit log" description="Accounts, role-based access and the audit trail of sign-ins, record views and changes." />
      <AdminView />
    </div>
  );
}
