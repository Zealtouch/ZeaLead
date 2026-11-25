import type { ReactNode } from "react";

// Two-panel sign-in layout from Leadscout: brand panel on the left, form on the right.
export function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="flex h-dvh">
      <div className="hidden flex-col items-center justify-center bg-primary p-12 text-center lg:flex lg:w-1/3">
        <div className="relative flex items-center justify-center">
          <div className="absolute size-80 rounded-full border border-primary-foreground/10" />
          <div className="absolute size-60 rounded-full border border-primary-foreground/15" />
          <div className="absolute size-40 rounded-full border border-primary-foreground/20" />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="leadscout" width={120} height={120} className="relative" />
        </div>
        <p className="mt-40 max-w-xs text-primary-foreground/70 text-sm">
          Finds the people already asking for a product like yours, with the quote that proves it.
        </p>
      </div>
      <div className="flex w-full items-center justify-center overflow-y-auto bg-background p-8 lg:w-2/3">
        <div className="w-full max-w-md space-y-10 py-24 lg:py-32">
          <div className="space-y-4 text-center">
            <h2 className="text-2xl font-medium tracking-tight">{title}</h2>
            <p className="mx-auto max-w-xl text-muted-foreground">{subtitle}</p>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
