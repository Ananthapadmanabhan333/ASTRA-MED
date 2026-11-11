import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Section container. `raised` is for the primary instrument on a page; everything else is
 * flat so the eye lands on one thing first.
 */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  raised = false,
  as: Tag = "section",
  id,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  raised?: boolean;
  as?: "section" | "div" | "article";
  id?: string;
}) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <Tag
      id={id}
      aria-labelledby={title ? headingId : undefined}
      className={cn(
        "min-w-0 rounded-lg border",
        raised ? "border-bulkhead bg-hull" : "border-bulkhead/70 bg-hull/55",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 pt-4 sm:px-5">
          <div className="min-w-0">
            {title && (
              <h2 id={headingId} className="font-heading text-lg font-semibold leading-tight text-foreground">
                {title}
              </h2>
            )}
            {description && <p className="mt-0.5 max-w-prose text-sm text-ink-2">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn("px-4 pt-3 pb-4 sm:px-5", bodyClassName)}>{children}</div>
    </Tag>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-heading text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-2 sm:text-base">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
