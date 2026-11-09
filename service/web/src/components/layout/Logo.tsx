import { cn } from "../../lib/utils";

/**
 * A small hexagonal lattice mark: three nodes connected through a ring.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      className={cn("size-8", className)}
      aria-hidden="true"
    >
      <path
        d="M16 2.8 27.4 9.4v13.2L16 29.2 4.6 22.6V9.4L16 2.8Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        opacity="0.55"
      />
      <path
        d="M16 8.4 22.4 12v7.2L16 22.8 9.6 19.2V12L16 8.4Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="8.4" r="2" fill="currentColor" />
      <circle cx="22.6" cy="19.4" r="2" fill="currentColor" />
      <circle cx="9.4" cy="19.4" r="2" fill="currentColor" />
    </svg>
  );
}
