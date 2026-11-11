import Link from "next/link";

import { EmptyState } from "@/components/data/states";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <EmptyState
      title="This page doesn't exist"
      action={
        <Button asChild size="sm" className="mt-2">
          <Link href="/">Go to mission control</Link>
        </Button>
      }
    >
      Check the address, or use the navigation to find the view you need.
    </EmptyState>
  );
}
