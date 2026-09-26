import outfitPreviews from "../../integrations/anima-outfit-previews.json";
import type { Template } from "./model";

// Matches getCharacterImageUrl in the pinned Anima Tools Hub, and clothing_data.js.
const HUB = "https://github.com/j955229/Comfyui-Anima-Tools-HUB";
export function templateSource(t: Template): string | undefined {
  if (
    t.source !== HUB ||
    t.source_revision !== "a0c351e81a24ebdbc7f47c524139a8dfe1226705" ||
    !t.source_key
  )
    return;
  if (t.kind === "character") {
    const [name, copyright] = t.source_key.split("||");
    return `https://blobs.animadex.net/Outputs/thumbs/${encodeURIComponent(copyright ? `${name}, ${copyright}` : name)}.webp`;
  }
  return (outfitPreviews as Record<string, string>)[t.source_key] || undefined;
}

export function templatePreview(t: Template): string | undefined {
  const generated = t.kind === "outfit" && t.source === "caster://curated-outfits-v1";
  if (!generated && !templateSource(t)) return;
  const version = encodeURIComponent(`${t.source_revision}:${t.source_key}`);
  return `/api/prompt-templates/${encodeURIComponent(t.id)}/image?v=${version}`;
}
