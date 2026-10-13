import type { ServerCharacter } from "./library";
import { APIError, apiURL, createHTTPClient } from "./api/http";
import type { components } from "./api/schema";

type Models = components["schemas"];
export type ProductionJob = Models["ProductionJob"];
export type ProductionState = ProductionJob["state"];
export type ProductionSpec = Models["ProductionSpec"];
export type ProductionAsset = Models["ProductionAsset"];
export type ProductionSnapshot = Models["ProductionSnapshot"];
export type ProductionPreset = Models["ProductionPreset"];
export type PromptSettings = Models["PromptSettings"];
export type PromptSettingsInput = Models["PromptSettingsUpdate"];
export type ProductionSelection = Models["ProductionSelection"];
export type OutfitVersion = Models["OutfitVersion"];
export type ProductionBatchRequest = Models["BatchRequest"];
export type ProductionBatch = Models["ProductionBatch"];
export class ProductionError extends APIError {}
export const productionStateNames: Record<ProductionState, string> = {
  queued: "排队中",
  submitting: "正在提交",
  running: "制作中",
  recovering: "正在恢复连接",
  submission_uncertain: "提交结果待核对",
  succeeded: "生成成功",
  failed: "失败",
  needs_correction: "待修正",
  cancelled: "已取消",
};
export function productionProgress(job: ProductionJob): number | undefined {
  if (job.state === "succeeded") return 100;
  const { value, max } =
    job.progress?.type === "progress"
      ? job.progress.data || {}
      : job.progress || {};
  return typeof value === "number" &&
    Number.isFinite(value) &&
    typeof max === "number" &&
    Number.isFinite(max) &&
    max > 0
    ? Math.min(100, Math.max(0, (value / max) * 100))
    : undefined;
}
export function productionAssetURL(id: string) {
  return apiURL(`/assets/${encodeURIComponent(id)}/file`);
}
export function createProductionAPI(fetcher: typeof fetch = fetch) {
  const http = createHTTPClient(fetcher);
  async function write<T>(
    path: string,
    body: unknown,
    method = "POST",
  ): Promise<T> {
    try {
      return await http.request<T>(path, {
        method,
        body: JSON.stringify(body),
      });
    } catch (error) {
      if (error instanceof APIError)
        throw new ProductionError(
          error.status === 409 ? "记录已变化，请刷新后重试。" : error.message,
          error.status,
          error.detail,
        );
      throw error;
    }
  }
  const characterPath = (id: string) =>
    `/production/characters/${encodeURIComponent(id)}`;
  return {
    async promptSettings(signal?: AbortSignal): Promise<PromptSettings> {
      return http.request("/prompt-settings", { signal }, 5000);
    },
    savePromptSettings(settings: PromptSettingsInput): Promise<PromptSettings> {
      return write("/prompt-settings", settings, "PUT");
    },
    async presets(signal?: AbortSignal): Promise<ProductionPreset[]> {
      return http.request("/production/pose-presets", { signal }, 5000);
    },
    savePreset(
      index: number,
      width = 1024,
      height = 1536,
    ): Promise<{ id: string; render_asset_id: string }> {
      return write(
        `/production/pose-presets/${index}?width=${width}&height=${height}`,
        {},
      );
    },
    async capabilities(signal?: AbortSignal): Promise<Models["Capabilities"]> {
      return http.request("/production/capabilities", { signal }, 5000);
    },
    createCharacter(character: ServerCharacter): Promise<ServerCharacter> {
      return write("/characters", character);
    },
    createOutfit(
      characterId: string,
      outfit: OutfitVersion,
    ): Promise<OutfitVersion> {
      return write(`${characterPath(characterId)}/outfits`, outfit);
    },
    select(
      characterId: string,
      selection: ProductionSelection,
      stage: "identity" | "outfit" | "pose",
      assetId: string,
      approve: boolean,
    ): Promise<ProductionSelection> {
      return write(
        `${characterPath(characterId)}/selection`,
        {
          expected_revision: selection.revision,
          stage,
          asset_id: assetId,
          approve,
        },
        "PUT",
      );
    },
    review(
      characterId: string,
      assetId: string,
      selection: ProductionSelection,
      decision: "accepted" | "rejected",
    ) {
      return write(
        `${characterPath(characterId)}/assets/${encodeURIComponent(assetId)}/review`,
        { expected_revision: selection.revision, decision },
        "PUT",
      );
    },
    submitBatch(
      characterId: string,
      request: ProductionBatchRequest,
    ): Promise<ProductionBatch> {
      // The caller persists this exact request before sending. No automatic
      // retry or regenerated key: uncertain responses must reuse the intent.
      return write(`${characterPath(characterId)}/batches`, request);
    },
    cancelQueued(job: ProductionJob): Promise<ProductionJob> {
      if (job.state !== "queued")
        return Promise.reject(new ProductionError("只能取消排队中的任务。"));
      return write(`/jobs/${encodeURIComponent(job.id)}/cancel`, {});
    },
    async snapshot(
      characterId: string,
      signal?: AbortSignal,
    ): Promise<ProductionSnapshot> {
      let data: ProductionSnapshot;
      try {
        data = await http.request(
          `/production/snapshot?character_id=${encodeURIComponent(characterId)}`,
          { signal },
          15000,
        );
      } catch (error) {
        if (error instanceof APIError)
          throw new ProductionError(
            error.status === 404
              ? "该角色的制作记录暂不可用。"
              : "制作记录连接失败，请稍后重试。",
            error.status,
          );
        throw error;
      }
      if (
        data.schema_version !== 1 ||
        !["characters", "jobs", "assets", "approvals", "poses"].every((key) =>
          Array.isArray(data[key as keyof ProductionSnapshot]),
        ) ||
        data.characters.some((c: ServerCharacter) => c.id !== characterId) ||
        data.jobs.some((j: ProductionJob) => !(j.state in productionStateNames))
      )
        throw Error("制作记录格式不兼容，未载入。");
      return data;
    },
  };
}
export const productionAPI = createProductionAPI();
