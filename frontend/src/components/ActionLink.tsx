import type { AnchorHTMLAttributes } from "react";

export function ActionLink({
  className = "",
  ...props
}: AnchorHTMLAttributes<HTMLAnchorElement>) {
  return <a {...props} className={`action-link ${className}`} />;
}
