import type { MouseEventHandler } from "react";
import banner from "../../../docs/images/caster-pixel-banner.png";

export function Brand({
  onClick,
}: {
  onClick?: MouseEventHandler<HTMLAnchorElement>;
}) {
  return (
    <a className="brand brand-banner" href="/" onClick={onClick}>
      <img src={banner} width={2172} height={724} alt="CASTER · 角色制作手账" />
    </a>
  );
}
