import type { ServerCharacter } from "./library";
export type ProductionState =
  | "queued"
  | "submitting"
  | "running"
  | "recovering"
  | "submission_uncertain"
  | "succeeded"
  | "failed"
  | "needs_correction"
  | "cancelled";
export type ProductionSpec = {
  asset_type?: string;
  character_id?: string;
  outfit_id?: string;
  expression?: string;
  action?: string;
};
export type ProductionAsset = {
  id: string;
  role: string;
  mode?: string;
  width?: number;
  height?: number;
  download_url: string;
  spec: ProductionSpec;
  parent_asset_id?: string;
  job_id?: string;
};
export type ProductionJob = {
  id: string;
  state: ProductionState;
  spec: ProductionSpec;
  outputs: string[];
  error?: string;
  created: number;
  progress?: {
    value?: number;
    max?: number;
    completed?: boolean;
    type?: string;
    data?: { value?: number; max?: number };
  };
  body: { reference_asset_id?: string; scene_spec_id: string };
};
export type ProductionSnapshot = {
  schema_version: 1;
  characters: ServerCharacter[];
  jobs: ProductionJob[];
  assets: ProductionAsset[];
  approvals: {
    id: string;
    asset_id: string;
    character_id: string;
    kind: "character" | "outfit" | "pose";
    outfit_id?: string;
  }[];
  poses: {
    id: string;
    render_asset_id: string;
    lighting_prompt?: string;
    preset_id?: number;
  }[];
  selections?: ProductionSelection[];
  batches?: ProductionBatch[];
  outfit_versions?: OutfitVersion[];
  reviews?: {
    asset_id: string;
    decision: "accepted" | "rejected";
    note: string;
  }[];
};
export type ProductionPreset = {
  id: number;
  name: string;
  source: string;
  revision: string;
  format: string;
  preview_url: string;
};
export type PromptSettings = {
  schema_version: 1;
  artist_style: string;
  fixed_positive: string;
  fixed_negative: string;
  content_hash: string;
  source: "default" | "saved";
  updated_at?: number | null;
};
export type PromptSettingsInput = Pick<
  PromptSettings,
  "artist_style" | "fixed_positive" | "fixed_negative"
>;
export type ProductionSelection = {
  character_id: string;
  revision: number;
  identity_asset_id: string | null;
  outfit_asset_id: string | null;
  outfit_id: string | null;
  pose_asset_id: string | null;
};
export type OutfitVersion = {
  id: string;
  name: string;
  tags: string[];
  description?: string;
  parent_id?: string | null;
};
export type ProductionBatchRequest = {
  canvas_preset?: string;
  idempotency_key: string;
  expected_revision: number;
  role: "identity" | "outfit" | "pose" | "expression" | "matte";
  candidates: {
    asset_id?: string;
    face_region?: [number, number, number, number];
    outfit_id?: string;
    pose_id?: string;
    expression?: string;
    seed: number;
  }[];
  retry_of?: string;
};
export type ProductionBatch = {
  id: string;
  character_id: string;
  job_ids: string[];
  source_asset_id: string | null;
  request: ProductionBatchRequest;
  created: number;
};
export class ProductionError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}
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
  return `/api/assets/${encodeURIComponent(id)}/file`;
}
export function createProductionAPI(fetcher: typeof fetch = fetch) {
  async function write(path: string, body: unknown, method = "POST") {
    const response = await fetcher(`/api${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) {
      let detail = "";
      try {
        detail = String((await response.json()).detail || "");
      } catch {
        /* gateway response */
      }
      throw new ProductionError(
        response.status === 409
          ? "记录已变化，请刷新后重试。"
          : `操作未完成（${response.status}）：${detail}`,
        response.status,
      );
    }
    return response.json();
  }
  const characterPath = (id: string) =>
    `/production/characters/${encodeURIComponent(id)}`;
  return {
    async promptSettings(signal?: AbortSignal): Promise<PromptSettings> {
      const response = await fetcher("/api/prompt-settings", {
        signal: signal
          ? AbortSignal.any([signal, AbortSignal.timeout(5000)])
          : AbortSignal.timeout(5000),
        cache: "no-store",
      });
      if (!response.ok)
        throw new ProductionError("提示词设置暂不可用。", response.status);
      return response.json();
    },
    savePromptSettings(settings: PromptSettingsInput): Promise<PromptSettings> {
      return write("/prompt-settings", settings, "PUT");
    },
    async presets(signal?: AbortSignal): Promise<ProductionPreset[]> {
      const r = await fetcher("/api/production/pose-presets", {
        signal: signal
          ? AbortSignal.any([signal, AbortSignal.timeout(5000)])
          : AbortSignal.timeout(5000),
      });
      if (!r.ok) throw new ProductionError("姿态目录暂不可用。", r.status);
      return r.json();
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
    async capabilities(signal?: AbortSignal): Promise<{
      selection: boolean;
      batches: boolean;
      generation_online: boolean;
    }> {
      const r = await fetcher("/api/production/capabilities", {
        signal: signal
          ? AbortSignal.any([signal, AbortSignal.timeout(5000)])
          : AbortSignal.timeout(5000),
        cache: "no-store",
      });
      if (!r.ok) throw new ProductionError("后端制作接口尚不可用。", r.status);
      return r.json();
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
      const response = await fetcher(
        `/api/production/snapshot?character_id=${encodeURIComponent(characterId)}`,
        {
          signal: signal
            ? AbortSignal.any([signal, AbortSignal.timeout(15000)])
            : AbortSignal.timeout(15000),
          cache: "no-store",
        },
      );
      if (!response.ok)
        throw Error(
          response.status === 404
            ? "该角色的制作记录暂不可用。"
            : "制作记录连接失败，请稍后重试。",
        );
      const data = await response.json();
      if (
        data.schema_version !== 1 ||
        !["characters", "jobs", "assets", "approvals", "poses"].every((key) =>
          Array.isArray(data[key]),
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
