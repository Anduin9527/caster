import { Images } from "@phosphor-icons/react";

export function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty-state">
      <Images size={46} weight="light" />
      <h3>{title}</h3>
      <p>{text}</p>
      <span className="dashed-note">每一次尝试，都会留下记录。</span>
    </div>
  );
}
