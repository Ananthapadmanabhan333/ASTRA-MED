import type { Metadata } from "next";

import { NotificationCentreView } from "@/components/screens/notification-centre-view";

export const metadata: Metadata = { title: "Notification Centre — ASTRA-MED" };

export default function NotificationCentrePage() {
  return <NotificationCentreView />;
}
