import type { Metadata } from "next";

import { AdminView } from "@/components/medical/admin-view";

export const metadata: Metadata = { title: "User & Role Management — ASTRA-MED" };

export default function AdminPage() {
  return <AdminView />;
}
