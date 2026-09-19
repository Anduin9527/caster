export type Kind = "character" | "outfit";
export type Template = {
  id: string;
  kind: Kind;
  name: string;
  display?: {
    name: string;
    categories: string[];
    tags: Record<string, string>;
  };
  trigger?: string;
  tags: string[];
  description?: string;
  categories?: string[];
  source?: string;
  source_revision?: string;
  source_key?: string;
};
export type Draft = { name: string; tags: string; description: string };
export type Outfit = {
  id: string;
  name: string;
  tags: string;
  baselineId?: string;
};
export type Character = {
  id: string;
  sourceId?: string;
  draft: Draft;
  identityId?: string;
  selectedOutfitAssetId?: string;
  selectedPoseId?: string;
  outfits: Outfit[];
};
export type Role = "identity" | "outfit" | "pose" | "expression";
export type Review = "pending" | "approved" | "rejected";
export type Asset = {
  id: string;
  characterId: string;
  characterName: string;
  outfitId: string;
  outfitName: string;
  role: Role;
  pose?: number;
  expression?: string;
  expressionPrompt?: string;
  parentId?: string;
  identityId?: string;
  baselineId?: string;
  draftKey: string;
  outfitKey: string;
  image: string;
  alpha?: string;
  source: string;
  review: Review;
  created: number;
  prompt: string;
};
export type JobState =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "needs_correction"
  | "cancelled";
export type Job = {
  id: string;
  batchId: string;
  state: JobState;
  progress: number;
  payload: Omit<
    Asset,
    "id" | "review" | "created" | "image" | "alpha" | "source"
  >;
  resultId?: string;
  outcome: "succeeded" | "failed" | "needs_correction";
  error?: string;
  retryOf?: string;
};
export type Mood = { id: string; name: string; prompt: string };
export type State = {
  version: 1;
  characters: Character[];
  activeId: string;
  step: number;
  outfitId: string;
  assets: Asset[];
  jobs: Job[];
  templates: Template[];
  moods: Mood[];
  offline: boolean;
  outfitPlans?: Record<string, string[]>;
  selections?: Record<string, { poses: number[]; moods: string[] }>;
};
export const steps = [
  "角色设定",
  "确认模样",
  "搭配服装",
  "选择姿态",
  "添加表情",
  "下载图片",
];
export const roleNames: Record<Role, string> = {
  identity: "身份候选",
  outfit: "换装候选",
  pose: "中性姿态",
  expression: "表情图片",
};
export const stateNames: Record<JobState, string> = {
  queued: "排队中",
  running: "制作中",
  succeeded: "生成成功",
  failed: "失败",
  needs_correction: "待修正",
  cancelled: "已取消",
};
let sequence = 0;
export const uid = () =>
  `${Date.now().toString(36)}-${(++sequence).toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
export const draftKey = (c: Character) => JSON.stringify(c.draft);
export const outfitKey = (o: Outfit) => JSON.stringify([o.name, o.tags]);
export const initialState = (): State => ({
  version: 1,
  activeId: "demo-b",
  step: 0,
  outfitId: "casual",
  characters: [
    {
      id: "demo-b",
      draft: {
        name: "林间旅人",
        tags: "1boy, brown hair, green eyes",
        description:
          "一位安静而好奇的年轻成年旅人。完整立绘，双脚可见，中性表情。",
      },
      outfits: [
        {
          id: "casual",
          name: "日常 · 米色夹克",
          tags: "beige jacket, green shirt, black pants, brown boots",
        },
      ],
    },
  ],
  assets: [],
  jobs: [],
  templates: [],
  moods: [
    { id: "happy", name: "开心", prompt: "a gentle happy smile" },
    { id: "surprised", name: "惊讶", prompt: "a surprised expression" },
    { id: "angry", name: "生气", prompt: "an angry expression" },
  ],
  offline: false,
});
export function current(s: State) {
  const c = s.characters.find((x) => x.id === s.activeId)!;
  const parent =
    s.step >= 3 && s.step <= 4
      ? s.assets.find((a) => a.id === c.selectedOutfitAssetId)
      : undefined;
  return {
    c,
    o:
      c.outfits.find((x) => x.id === (parent?.outfitId || s.outfitId)) ||
      c.outfits[0],
  };
}
export function identityReady(s: State, c: Character) {
  return s.assets.some(
    (a) =>
      a.id === c.identityId &&
      a.review === "approved" &&
      a.draftKey === draftKey(c),
  );
}
export function outfitReady(s: State, c: Character, o: Outfit) {
  return (
    identityReady(s, c) &&
    s.assets.some(
      (a) =>
        a.id === o.baselineId &&
        a.review === "approved" &&
        a.outfitKey === outfitKey(o) &&
        (a.role === "identity"
          ? a.id === c.identityId
          : a.identityId === c.identityId),
    )
  );
}
export function selectedOutfit(s: State, c: Character) {
  const asset = s.assets.find(
    (a) =>
      a.id === c.selectedOutfitAssetId &&
      a.characterId === c.id &&
      a.role === "outfit",
  );
  if (!asset) return undefined;
  const outfit = c.outfits.find((o) => o.id === asset.outfitId);
  return outfit &&
    outfit.baselineId === asset.id &&
    asset.draftKey === draftKey(c) &&
    outfitReady(s, c, outfit)
    ? { asset, outfit }
    : undefined;
}
export function poseReady(s: State, c: Character, _o?: Outfit) {
  const chosen = selectedOutfit(s, c);
  if (!chosen) return [];
  return s.assets.filter(
    (a) =>
      a.id === c.selectedPoseId &&
      a.characterId === c.id &&
      a.outfitId === chosen.outfit.id &&
      a.role === "pose" &&
      a.review === "approved" &&
      a.baselineId === chosen.asset.id &&
      a.identityId === c.identityId &&
      a.draftKey === draftKey(c) &&
      a.outfitKey === outfitKey(chosen.outfit),
  );
}
export function canStep(s: State, step: number) {
  const { c } = current(s);
  return (
    step <= 1 ||
    step === 5 ||
    (step === 2
      ? identityReady(s, c)
      : step === 3
        ? Boolean(selectedOutfit(s, c))
        : poseReady(s, c).length === 1)
  );
}
export function composedPrompt(c: Character, o: Outfit) {
  return `solo, full body, ${c.draft.tags}, ${o.tags}. ${c.draft.description}`;
}
export type Enqueue = {
  role: Role;
  poses?: number[];
  moods?: string[];
  count?: number;
  outfitIds?: string[];
  scenario?: "success" | "mixed" | "failed" | "needs_correction";
};
export function enqueue(s: State, req: Enqueue): State {
  const { c } = current(s);
  if (req.role === "outfit" && req.outfitIds) {
    const ids = [...new Set(req.outfitIds)];
    if (!ids.length || ids.some((id) => !c.outfits.some((o) => o.id === id)))
      throw Error("请选择要尝试的服装。");
    const batchId = uid();
    const start = s.jobs.length;
    let next = s;
    for (const id of ids)
      next = enqueue(
        { ...next, outfitId: id },
        { ...req, outfitIds: undefined },
      );
    return {
      ...next,
      outfitId: s.outfitId,
      jobs: next.jobs.map((j, i) => (i >= start ? { ...j, batchId } : j)),
    };
  }
  const chosen = selectedOutfit(s, c);
  const o =
    req.role === "pose" || req.role === "expression"
      ? chosen?.outfit
      : req.role === "identity"
        ? { ...c.outfits[0], name: "基础服装", tags: "simple neutral clothing" }
        : c.outfits.find((o) => o.id === s.outfitId) || c.outfits[0];
  if (!o) throw Error("请先选定一张服装图片。");
  if (
    !c.draft.name.trim() ||
    !c.draft.tags.trim() ||
    !o.name.trim() ||
    !o.tags.trim()
  )
    throw Error("请填写角色名称、外观标签与服装信息。");
  if (req.role === "outfit" && !identityReady(s, c))
    throw Error("请先确认当前角色身份。");
  if ((req.role === "pose" || req.role === "expression") && !chosen)
    throw Error("请先选定一张服装图片。");
  const batchId = uid();
  const base = {
    characterId: c.id,
    characterName: c.draft.name,
    outfitId: o.id,
    outfitName: o.name,
    role: req.role,
    draftKey: draftKey(c),
    outfitKey: outfitKey(o),
    identityId: c.identityId,
    baselineId: o.baselineId,
    prompt: composedPrompt(c, o),
  };
  let payloads: Job["payload"][] = [];
  if (req.role === "identity" || req.role === "outfit")
    payloads = Array.from({ length: req.count || 1 }, () => ({
      ...base,
      parentId: req.role === "outfit" ? c.identityId : undefined,
    }));
  if (req.role === "pose")
    payloads = [...new Set(req.poses || [])].map((pose) => ({
      ...base,
      pose,
      parentId: o.baselineId,
    }));
  if (req.role === "expression") {
    const latest = poseReady(s, c);
    if (req.poses?.some((p) => p !== latest[0]?.pose))
      throw Error("表情只能使用当前选中的一张姿态图片。");
    for (const parent of latest)
      for (const mood of s.moods.filter((m) => req.moods?.includes(m.id)))
        payloads.push({
          ...base,
          pose: parent.pose,
          expression: mood.name,
          expressionPrompt: mood.prompt,
          parentId: parent.id,
          prompt: `Change only the facial expression to ${mood.prompt}. Preserve identity, hair, clothing, framing and background.`,
        });
  }
  if (!payloads.length) throw Error("请选择至少一个可用姿态和所需表情。");
  const jobs: Job[] = payloads.map((payload, i) => ({
    id: uid(),
    batchId,
    state: "queued",
    progress: 0,
    payload,
    outcome:
      req.scenario === "mixed"
        ? i % 3 === 1
          ? "failed"
          : i % 3 === 2
            ? "needs_correction"
            : "succeeded"
        : req.scenario === "failed"
          ? "failed"
          : req.scenario === "needs_correction"
            ? "needs_correction"
            : "succeeded",
  }));
  return { ...s, jobs: [...s.jobs, ...jobs] };
}
export function tick(s: State): State {
  if (s.offline) return s;
  const job =
    s.jobs.find((j) => j.state === "running") ||
    s.jobs.find((j) => j.state === "queued");
  if (!job) return s;
  if (job.state === "queued")
    return {
      ...s,
      jobs: s.jobs.map((j) =>
        j.id === job.id ? { ...j, state: "running", progress: 10 } : j,
      ),
    };
  const progress = Math.min(100, job.progress + 30);
  if (progress < 100)
    return {
      ...s,
      jobs: s.jobs.map((j) => (j.id === job.id ? { ...j, progress } : j)),
    };
  const resultId = job.outcome === "succeeded" ? uid() : undefined;
  const p = job.payload;
  let image = "/demo-assets/identity.png",
    alpha: string | undefined;
  if (p.role === "pose") {
    const n = (((p.pose || 1) - 1) % 3) + 1;
    image = `/demo-assets/pose-${n}.png`;
    alpha = `/demo-assets/pose-${n}-alpha.png`;
  }
  if (p.role === "expression") {
    const mood =
      p.expression === "惊讶"
        ? "surprised"
        : p.expression === "生气"
          ? "angry"
          : "happy";
    image = `/demo-assets/${mood}.png`;
    alpha = `/demo-assets/${mood}-alpha.png`;
  }
  const assets = resultId
    ? [
        ...s.assets,
        {
          ...p,
          id: resultId,
          review: "pending" as Review,
          created: Date.now(),
          image,
          alpha,
          source:
            p.role === "outfit"
              ? "换装设计示意 · 复用 B 身份图，未真实换装"
              : "历史样例 B · 不代表当前输入或所选预设的生成效果",
        },
      ]
    : s.assets;
  return {
    ...s,
    assets,
    jobs: s.jobs.map((j) =>
      j.id === job.id
        ? {
            ...j,
            progress: 100,
            state: j.outcome,
            resultId,
            error:
              j.outcome === "failed"
                ? "模拟生成失败，请检查配置后重新提交。"
                : j.outcome === "needs_correction"
                  ? "模拟人脸检测／手部遮挡问题，请调整预设后重新提交。"
                  : undefined,
          }
        : j,
    ),
  };
}
export function reviewAsset(s: State, id: string, review: Review): State {
  const asset = s.assets.find((a) => a.id === id);
  if (!asset) throw Error("图片不存在。");
  const c = s.characters.find((c) => c.id === asset.characterId)!;
  const o = c.outfits.find((o) => o.id === asset.outfitId)!;
  if (review === "approved") {
    if (
      ["pose", "expression"].includes(asset.role) &&
      (!outfitReady(s, c, o) ||
        selectedOutfit(s, c)?.asset.id !== asset.baselineId)
    )
      throw Error("服装或身份基准尚未确认，请先完成基准确认。");
    if (asset.role !== "identity" && !identityReady(s, c))
      throw Error("身份基准尚未确认，请先完成身份确认。");
    if (
      asset.draftKey !== draftKey(c) ||
      (asset.role !== "identity" && asset.outfitKey !== outfitKey(o))
    )
      throw Error("设定已改变，此图仅保留为历史候选，请生成新版本。");
    if (asset.role !== "identity" && asset.identityId !== c.identityId)
      throw Error("身份基准已改变，请生成新候选。");
    if (
      (asset.role === "pose" || asset.role === "expression") &&
      asset.baselineId !== o.baselineId
    )
      throw Error("服装基准已改变，请生成新候选。");
    if (
      asset.role === "expression" &&
      !poseReady(s, c, o).some((p) => p.id === asset.parentId)
    )
      throw Error("父姿态未通过当前审阅。");
  }
  const updated = {
    ...s,
    assets: s.assets.map((a) => (a.id === id ? { ...a, review } : a)),
  };
  if (review === "approved") {
    updated.characters = s.characters.map((ch) =>
      ch.id !== c.id
        ? ch
        : {
            ...ch,
            ...(asset.role === "identity"
              ? {
                  identityId: id,
                  selectedOutfitAssetId: undefined,
                  selectedPoseId: undefined,
                }
              : {}),
            ...(asset.role === "outfit"
              ? {
                  selectedOutfitAssetId: id,
                  selectedPoseId:
                    ch.selectedOutfitAssetId === id
                      ? ch.selectedPoseId
                      : undefined,
                }
              : {}),
            ...(asset.role === "pose" ? { selectedPoseId: id } : {}),
            outfits: ch.outfits.map((out) =>
              out.id === o.id && asset.role === "outfit"
                ? { ...out, baselineId: id }
                : out,
            ),
          },
    );
    if (asset.role === "outfit" && s.activeId === c.id) updated.outfitId = o.id;
  }
  return updated;
}
export function cancelJob(s: State, id: string): State {
  const j = s.jobs.find((j) => j.id === id);
  if (j?.state !== "queued") throw Error("只能取消排队任务。");
  return {
    ...s,
    jobs: s.jobs.map((j) => (j.id === id ? { ...j, state: "cancelled" } : j)),
  };
}
export function retryJob(s: State, id: string): State {
  const old = s.jobs.find((j) => j.id === id);
  if (!old || !["failed", "needs_correction"].includes(old.state))
    throw Error("此任务不能重新提交。");
  const c = s.characters.find((c) => c.id === old.payload.characterId)!;
  const o = c.outfits.find((o) => o.id === old.payload.outfitId)!;
  if (
    draftKey(c) !== old.payload.draftKey ||
    (old.payload.role !== "identity" &&
      outfitKey(o) !== old.payload.outfitKey) ||
    (old.payload.role !== "identity" &&
      (!identityReady(s, c) || old.payload.identityId !== c.identityId)) ||
    (["pose", "expression"].includes(old.payload.role) &&
      (!outfitReady(s, c, o) ||
        old.payload.baselineId !== selectedOutfit(s, c)?.asset.id)) ||
    (old.payload.role === "expression" &&
      !poseReady(s, c, o).some((p) => p.id === old.payload.parentId))
  )
    throw Error("基准或设定已改变，请从当前步骤创建新任务。");
  return {
    ...s,
    jobs: [
      ...s.jobs,
      {
        ...old,
        id: uid(),
        batchId: uid(),
        state: "queued",
        progress: 0,
        error: undefined,
        resultId: undefined,
        outcome: "succeeded",
        retryOf: id,
      },
    ],
  };
}
export function parseBundle(text: string): Template[] {
  const b = JSON.parse(text);
  if (
    b.schema_version !== 1 ||
    !Array.isArray(b.templates) ||
    b.templates.length > 10000
  )
    throw Error("需要 schema_version: 1 与 templates 数组（最多 10000 项）。");
  const seen = new Set();
  for (const t of b.templates) {
    if (!t || typeof t !== "object") throw Error("模板必须为对象");
    for (const key of [
      "trigger",
      "description",
      "source",
      "source_revision",
      "source_key",
    ])
      if (t[key] !== undefined && typeof t[key] !== "string")
        throw Error("模板文本字段必须为字符串");
    if (
      typeof t.id !== "string" ||
      !/^[a-zA-Z0-9_-]{1,128}$/.test(t.id) ||
      seen.has(t.id) ||
      !["character", "outfit"].includes(t.kind) ||
      typeof t.name !== "string" ||
      !t.name.trim() ||
      !Array.isArray(t.tags) ||
      !t.tags.every((x: unknown) => typeof x === "string") ||
      (t.trigger !== undefined && typeof t.trigger !== "string") ||
      (t.description !== undefined && typeof t.description !== "string") ||
      (t.categories !== undefined &&
        (!Array.isArray(t.categories) ||
          !t.categories.every((x: unknown) => typeof x === "string")))
    )
      throw Error("模板字段无效或 ID 重复。");
    if (
      ![t.trigger, ...t.tags, t.description].some(
        (x) => typeof x === "string" && x.trim(),
      )
    )
      throw Error("模板提示词不能为空。");
    seen.add(t.id);
  }
  return b.templates;
}
export function importTemplates(s: State, items: Template[]): State {
  for (const t of items) {
    const old = s.templates.find((x) => x.id === t.id);
    if (old && JSON.stringify(old) !== JSON.stringify(t))
      throw Error(`模板 ${t.id} 已存在且内容不同；请修改 ID 后导入。`);
  }
  return {
    ...s,
    templates: [
      ...s.templates,
      ...items.filter((t) => !s.templates.some((x) => x.id === t.id)),
    ],
  };
}
