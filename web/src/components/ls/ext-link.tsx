import type { ReactNode } from "react";

import { ExternalLink } from "lucide-react";

import { safeHref } from "@/lib/format";
import { cn } from "@/lib/utils";

// Links to collected posts and profiles. The URL comes from attacker-written pages,
// so only http(s) becomes a link; the page opens without a referrer or opener.
export function ExtLink({
  href,
  children,
  className,
  icon = true,
}: {
  href: string | null | undefined;
  children?: ReactNode;
  className?: string;
  icon?: boolean;
}) {
  const url = safeHref(href);
  if (!url) return <span className={className}>{children ?? href ?? "—"}</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={cn("inline-flex min-w-0 items-center gap-1 text-primary underline-offset-2 hover:underline", className)}
    >
      <span className="truncate">{children ?? url}</span>
      {icon && <ExternalLink className="size-3 shrink-0 opacity-60" aria-hidden="true" />}
    </a>
  );
}
