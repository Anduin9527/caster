import { apiURL } from "../api/http";
import type { ImgHTMLAttributes } from "react";

export function AssetThumbnail({
  assetId,
  alt,
  ...props
}: Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "srcSet"> & {
  assetId: string;
  alt: string;
}) {
  const url = apiURL(`/assets/${encodeURIComponent(assetId)}/thumbnail`);
  return (
    <img
      loading="lazy"
      decoding="async"
      {...props}
      alt={alt}
      src={`${url}?size=768&v=2`}
      srcSet={`${url}?size=768&v=2 1x, ${url}?size=1536&v=2 2x`}
    />
  );
}
