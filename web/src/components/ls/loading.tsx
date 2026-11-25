import { Spinner } from "@/components/ui/spinner";

export function Loading({ className = "min-h-36" }: { className?: string }) {
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <Spinner />
    </div>
  );
}

export function EmptyRow({ text }: { text: string }) {
  return <div className="py-12 text-center text-muted-foreground text-sm">{text}</div>;
}
