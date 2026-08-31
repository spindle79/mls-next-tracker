/**
 * Shared presentational primitives for tracker panels — scroll wrappers, repeated
 * table patterns, rank/GD formatting, and loading/error messages. Keeps styling in CSS
 * (`globals.css` `.tracker-*`) instead of duplicated inline styles.
 */
import type { ReactNode } from "react";

export function TableScroll({
  children,
  className,
  id,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <div id={id} className={["tracker-table-scroll", className].filter(Boolean).join(" ")}>
      {children}
    </div>
  );
}

/**
 * Rank position change: positive = moved up (better). Use `neutral="dash"` for a “-” when no change.
 */
export function RankDelta({ diff, neutral = "omit" }: { diff: number; neutral?: "omit" | "dash" }) {
  if (diff > 0) return <span className="change-indicator change-up">+{diff}</span>;
  if (diff < 0) return <span className="change-indicator change-down">{diff}</span>;
  if (neutral === "dash") return <span className="change-indicator change-none">-</span>;
  return null;
}

export function GoalDiffTd({ gd }: { gd: number | undefined }) {
  const v = gd ?? 0;
  const tone = v > 0 ? "gd-pos" : v < 0 ? "gd-neg" : "gd-zero";
  return (
    <td className={`num ${tone}`}>
      {v > 0 ? "+" : ""}
      {v}
    </td>
  );
}

export function EmptyTableRow({
  colSpan,
  center,
  children,
}: {
  colSpan: number;
  center?: boolean;
  children: ReactNode;
}) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        className={
          center ? "tracker-table-empty tracker-table-empty--center" : "tracker-table-empty"
        }
      >
        {children}
      </td>
    </tr>
  );
}

export function TrackerState({
  variant,
  children,
}: {
  variant: "loading" | "error";
  children: ReactNode;
}) {
  return (
    <div className="container">
      <p
        className={`tracker-state ${variant === "error" ? "tracker-state--error" : "tracker-state--muted"}`}
      >
        {children}
      </p>
    </div>
  );
}
