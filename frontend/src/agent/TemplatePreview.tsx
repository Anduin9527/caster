import { useState } from "react";

function localTemplatePreview(value?: string | null) {
  if (!value?.startsWith("/prompt-templates/")) return "";
  return "/api" + value;
}

export function TemplatePreview({
  src,
  alt,
}: {
  src?: string | null;
  alt: string;
}) {
  const [failed, setFailed] = useState(false);
  const local = localTemplatePreview(src);
  if (!local || failed) return null;
  return (
    <img
      className="agent-template-preview"
      src={local}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
