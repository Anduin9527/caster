import canvasPresets from "../../integrations/canvas-presets.json";
import {
  expressionPresets as moods,
  expressionLabel,
  assetTypeLabel,
  jobErrorLabel,
} from "./presentation";
import { Select } from "./Select";
import { useEffect, useState, useRef } from "react";
import {
  ArrowRight,
  Clock,
  X,
  SlidersHorizontal,
  Plus,
  DownloadSimple,
} from "@phosphor-icons/react";
import { Modal, TemplateDrawer } from "./App";
import { serverLibrary, type ServerCharacter } from "./library";
import { type Template, steps } from "./model";
import {
  productionAPI,
  productionAssetURL,
  productionStateNames,
  productionProgress,
  ProductionError,
  type ProductionSnapshot,
  type ProductionSelection,
  type ProductionAsset,
  type ProductionBatchRequest,
  type ProductionBatch,
  type ProductionPreset,
} from "./production";
import "./live.css";

const FORM_KEY = "caster-live-character-draft-v1";
const ACTIVE_KEY = "caster-live-active-v1";
const newCharacter = (): ServerCharacter => ({
  id: crypto.randomUUID(),
  name: "",
  fixed_tags: [],
  description: "",
  outfits: [],
});
function readDraft(): ServerCharacter {
  try {
    return (
      JSON.parse(localStorage.getItem(FORM_KEY) || "null") || newCharacter()
    );
  } catch {
    return newCharacter();
  }
}
function emptySelection(id: string): ProductionSelection {
  return {
    character_id: id,
    revision: 0,
    identity_asset_id: null,
    outfit_asset_id: null,
    outfit_id: null,
    pose_asset_id: null,
  };
}
const intentKey = (id: string) => `caster-production-intent-${id}`;
function readIntent(id: string): ProductionBatchRequest | null {
  try {
    return JSON.parse(localStorage.getItem(intentKey(id)) || "null");
  } catch {
    return null;
  }
}

export function LiveWorkbench() {
  const [characters, setCharacters] = useState<ServerCharacter[]>([]);
  const [active, setActive] = useState(
    () => localStorage.getItem(ACTIVE_KEY) || "",
  );
  const [draft, setDraft] = useState(readDraft);
  const [step, setStep] = useState(0);
  const [canvasPreset, setCanvasPreset] = useState(() => {
    const saved=localStorage.getItem("caster-canvas-preset");
    return canvasPresets.some(p=>p.id===saved) ? saved! : "1024x1536";
  });
  useEffect(()=>localStorage.setItem("caster-canvas-preset",canvasPreset),[canvasPreset]);
  const [characterFormOpen, setCharacterFormOpen] = useState(false);
  const skipPreferencesSave = useRef(true);
  const stepsNav = useRef<HTMLElement>(null);
  useEffect(() => {
    const nav = stepsNav.current;
    if (!nav) return;
    const reveal = () => {
      const item = nav.querySelector<HTMLElement>('[aria-current="step"]');
      if (!item || nav.scrollWidth <= nav.clientWidth) return;
      const a = item.getBoundingClientRect(),
        b = nav.getBoundingClientRect();
      nav.scrollLeft += a.left - b.left - (nav.clientWidth - a.width) / 2;
    };
    reveal();
    const resize = new ResizeObserver(reveal);
    resize.observe(nav);
    return () => resize.disconnect();
  }, [step]);
  const [snapshot, setSnapshot] = useState<ProductionSnapshot | null>(null);
  const catalog: Template[] = [];
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [connected, setConnected] = useState(false);
  const [online, setOnline] = useState(false);
  const [drawer, setDrawer] = useState<"character" | "outfit" | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [tasksOpen, setTasksOpen] = useState(false);
  const [wideScreen, setWideScreen] = useState(
    () => window.matchMedia("(min-width: 1100px)").matches,
  );
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1100px)");
    const change = () => setWideScreen(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  const [outfitForm, setOutfitForm] = useState<{
    id: string;
    name: string;
    tags: string;
    parent_id?: string;
  } | null>(null);
  const [outfitIds, setOutfitIds] = useState<string[]>([]);
  const [presets, setPresets] = useState<ProductionPreset[]>([]);
  const [presetError, setPresetError] = useState("");
  const [poseIds, setPoseIds] = useState<string[]>([]);
  const [expressions, setExpressions] = useState(moods);
  const [chosenMoods, setChosenMoods] = useState(
    moods.slice(0, 3).map((m) => m.prompt),
  );
  const [customMood, setCustomMood] = useState("");
  const [lightbox, setLightbox] = useState<ProductionAsset | null>(null);
  const [pending, setPending] = useState<ProductionBatchRequest | null>(() =>
    readIntent(active),
  );
  const [filter, setFilter] = useState("all");
  const [alpha, setAlpha] = useState(false);
  const [correction, setCorrection] = useState<{
    batch: ProductionBatch;
    index: number;
    region: string[];
  } | null>(null);
  const [expressionFilter, setExpressionFilter] = useState("all");
  const character = characters.find((c) => c.id === active);
  const data = snapshot?.characters.some((c) => c.id === active)
    ? snapshot
    : null;
  const selection =
    data?.selections?.find((s) => s.character_id === active) ||
    emptySelection(active);
  const assets = data?.assets || [];
  const selectedImage = (id: string | null) => assets.find((a) => a.id === id);
  const outfitName = (id?: string) =>
    data?.outfit_versions?.find((o) => o.id === id)?.name || "基础服装";
  const expressionName = (prompt?: string) =>
    expressionLabel(prompt, expressions);
  const assetTypeName = assetTypeLabel;
  const canStep = (n: number) =>
    n === 0 || n === 5
      ? true
      : n === 1
        ? Boolean(character)
        : n === 2
          ? Boolean(selection.identity_asset_id)
          : n === 3
            ? Boolean(selection.outfit_asset_id)
            : Boolean(selection.pose_asset_id);
  function go(n: number) {
    if (canStep(n)) {
      setStep(n);
      setSettingsOpen(false);
      window.scrollTo({ top: 0 });
    }
  }
  useEffect(() => {
    localStorage.setItem(FORM_KEY, JSON.stringify(draft));
  }, [draft]);
  useEffect(() => {
    localStorage.setItem(ACTIVE_KEY, active);
    setPending(readIntent(active));
    skipPreferencesSave.current = true;
    try {
      const saved = JSON.parse(
        localStorage.getItem(`caster-live-options-${active}`) || "null",
      );
      if (saved) {
        if (Number.isInteger(saved.step) && saved.step >= 0 && saved.step <= 5)
          setStep(saved.step);
        setOutfitIds(Array.isArray(saved.outfitIds) ? saved.outfitIds : []);
        setPoseIds(
          Array.isArray(saved.poseIds)
            ? saved.poseIds.filter((id: string) =>
                /^preset:1[0-9]{2}$/.test(id),
              )
            : [],
        );
        setExpressions([
          ...moods,
          ...(Array.isArray(saved.expressions) ? saved.expressions : []).filter(
            (item: { prompt: string }) =>
              !moods.some((m) => m.prompt === item.prompt),
          ),
        ]);
        if (Array.isArray(saved.chosenMoods)) setChosenMoods(saved.chosenMoods);
      } else {
        setExpressions(moods);
        setChosenMoods(moods.slice(0, 3).map((m) => m.prompt));
        setOutfitIds([]);
        setPoseIds([]);
      }
    } catch {
      setOutfitIds([]);
      setPoseIds([]);
    }
  }, [active]);
  useEffect(() => {
    if (skipPreferencesSave.current) {
      skipPreferencesSave.current = false;
      return;
    }
    if (active)
      localStorage.setItem(
        `caster-live-options-${active}`,
        JSON.stringify({ step, outfitIds, poseIds, expressions, chosenMoods }),
      );
  }, [active, step, outfitIds, poseIds, expressions, chosenMoods]);
  useEffect(() => {
    let live = true;
    serverLibrary
      .characters()
      .then((rows) => {
        if (!live) return;
        setCharacters(rows);
        setActive((old) =>
          rows.some((c) => c.id === old) ? old : rows[0]?.id || "",
        );
      })
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    setConnected(false);

    async function load() {
      try {
        const [cap, snap] = await Promise.all([
          productionAPI.capabilities(),
          active
            ? productionAPI.snapshot(active, controller.signal)
            : Promise.resolve(null),
        ]);
        if (!live) return;
        setConnected(Boolean(cap.selection && cap.batches));
        setOnline(cap.generation_online);
        productionAPI
          .presets()
          .then((rows) => {
            if (live) {
              const studio = rows.filter((p) => p.format === "pose_studio_3d");
              setPresets(studio);
              setPresetError(
                studio.length ? "" : "姿态库暂不可用，请稍后重试。",
              );
              const available = new Set(studio.map((p) => `preset:${p.id}`));
              setPoseIds((previous) => {
                const valid = previous.filter((id) => available.has(id));
                return valid.length === previous.length ? previous : valid;
              });
            }
          })
          .catch(() => {
            if (live) setPresetError("姿态库连接失败，正在重新连接。");
          });
        setSnapshot(snap);
        setError("");
        if (snap)
          setCharacters((rows) =>
            rows.map((c) => snap.characters.find((v) => v.id === c.id) || c),
          );
      } catch (e) {
        if (live) {
          setConnected(false);
          setError((e as Error).message);
        }
      } finally {
        if (live) timer = setTimeout(load, 5000);
      }
    }
    void load();
    return () => {
      live = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [active, revision]);
  useEffect(() => {
    if (data && !canStep(step)) setStep(character ? 1 : 0);
  }, [selection.revision, active]);
  async function act(action: () => Promise<void>) {
    if (busy) return false;
    setBusy(true);
    setNotice("");
    try {
      await action();
      setRevision((v) => v + 1);
      return true;
    } catch (e) {
      setNotice((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  function toggle(value: string, values: string[], set: (v: string[]) => void) {
    set(
      values.includes(value)
        ? values.filter((v) => v !== value)
        : [...values, value],
    );
  }
  async function choose(
    asset: ProductionAsset,
    stage: "identity" | "outfit" | "pose",
  ) {
    await act(async () => {
      await productionAPI.select(active, selection, stage, asset.id, true);
      setNotice("已选定图片。");
      setLightbox(null);
    });
  }
  async function submit(request?: ProductionBatchRequest) {
    const role = ["", "identity", "outfit", "pose", "expression"][
      step
    ] as ProductionBatchRequest["role"];
    const candidates =
      role === "identity"
        ? [0, 1, 2].map(() => ({ seed: Math.floor(Math.random() * 2 ** 32) }))
        : role === "outfit"
          ? outfitIds.flatMap((outfit_id) =>
              [0, 1, 2].map(() => ({
                outfit_id,
                seed: Math.floor(Math.random() * 2 ** 32),
              })),
            )
          : role === "pose"
            ? poseIds.map((pose_id) => ({
                pose_id,
                seed: Math.floor(Math.random() * 2 ** 32),
              }))
            : chosenMoods.map((expression) => ({
                expression,
                seed: Math.floor(Math.random() * 2 ** 32),
              }));
    const intent: ProductionBatchRequest = request || {
      role,
      ...(role === "identity" ? {canvas_preset: canvasPreset} : {}),
      candidates,
      expected_revision: selection.revision,
      idempotency_key: crypto.randomUUID(),
    };
    return act(async () => {
      // The transparency button is the user's explicit choice of source image.
      // Keep that selection inside the same busy section as submission.
      if (intent.role === "matte") {
        for (const candidate of intent.candidates) {
          const asset = assets.find((a) => a.id === candidate.asset_id);
          if (
            asset?.spec.asset_type === "expression" &&
            !data?.reviews?.some(
              (r) => r.asset_id === asset.id && r.decision === "accepted",
            )
          ) {
            await productionAPI.review(active, asset.id, selection, "accepted");
          }
        }
      }
      if (!request && role === "pose") {
        for (const item of intent.candidates)
          if (item.pose_id?.startsWith("preset:")) {
            const saved = await productionAPI.savePreset(
              Number(item.pose_id.slice(7)),
              selectedImage(selection.outfit_asset_id)?.width || 1024,
              selectedImage(selection.outfit_asset_id)?.height || 1536,
            );
            item.pose_id = saved.id;
          }
      }
      localStorage.setItem(intentKey(active), JSON.stringify(intent));
      setPending(intent);
      try {
        const batch = await productionAPI.submitBatch(active, intent);
        localStorage.removeItem(intentKey(active));
        setPending(null);
        setNotice(`已提交 ${batch.job_ids.length} 项任务。`);
      } catch (e) {
        if (e instanceof ProductionError && e.status && e.status < 500) {
          localStorage.removeItem(intentKey(active));
          setPending(null);
        }
        throw e;
      }
    });
  }
  const stage = step === 1 ? "identity" : step === 2 ? "outfit" : "pose";
  const selectedId =
    step === 1
      ? selection.identity_asset_id
      : step === 2
        ? selection.outfit_asset_id
        : selection.pose_asset_id;
  const outputKind =
    step === 1
      ? "sprite"
      : step === 2
        ? "outfit"
        : step === 3
          ? "pose"
          : "expression";
  const successful = (asset: ProductionAsset) =>
    data?.jobs.some(
      (j) => j.state === "succeeded" && j.outputs.includes(asset.id),
    );
  const candidates = assets.filter(
    (a) =>
      a.role === "original" &&
      a.spec.asset_type === outputKind &&
      successful(a) &&
      (step === 2
        ? a.parent_asset_id === selection.identity_asset_id
        : step === 3
          ? a.parent_asset_id === selection.outfit_asset_id
          : step === 4
            ? a.parent_asset_id === selection.pose_asset_id
            : true),
  );
  const source = selectedImage(
    step === 2
      ? selection.identity_asset_id
      : step === 3
        ? selection.outfit_asset_id
        : selection.pose_asset_id,
  );
  function canMatte(asset: ProductionAsset) {
    return (
      asset.role === "original" &&
      successful(asset) &&
      ((asset.spec.asset_type === "expression" &&
        asset.parent_asset_id === selection.pose_asset_id) ||
        data?.reviews?.some(
          (r) => r.asset_id === asset.id && r.decision === "accepted",
        ) ||
        data?.approvals.some((a) => a.asset_id === asset.id))
    );
  }
  function makeTransparent(asset: ProductionAsset) {
    return submit({
      role: "matte",
      expected_revision: selection.revision,
      idempotency_key: crypto.randomUUID(),
      candidates: [{ asset_id: asset.id, seed: 9527 }],
    });
  }
  function card(asset: ProductionAsset, selectable = false) {
    const checked = selectedId === asset.id;
    return (
      <article
        key={asset.id}
        className={`asset-card ${checked && selectable ? "selected-candidate" : ""}`}
      >
        <button
          className="asset-image"
          onClick={() => setLightbox(asset)}
          aria-label={`查看图片 ${asset.id.slice(0, 6)}`}
        >
          <img
            loading="lazy"
            decoding="async"
            src={`/api/assets/${encodeURIComponent(asset.id)}/thumbnail`}
            alt={`${outfitName(asset.spec.outfit_id)} · ${expressionName(asset.spec.expression)}`}
          />
        </button>
        <div className="asset-info">
          <strong>
            {asset.spec.expression &&
            asset.spec.expression !== "neutral expression"
              ? expressionName(asset.spec.expression)
              : outfitName(asset.spec.outfit_id)}
          </strong>
          {step === 5 && canMatte(asset) && (
            <button
              disabled={busy || !online || !!pending}
              onClick={() => void makeTransparent(asset)}
            >
              制作透明图片
            </button>
          )}
          {selectable ? (
            <label className="candidate-choice">
              <input
                type="radio"
                name={`choice-${stage}`}
                checked={checked}
                disabled={busy || !connected}
                onChange={() => void choose(asset, stage)}
              />
              {checked ? "已选中" : "选择这张"}
            </label>
          ) : (
            <a href={productionAssetURL(asset.id)} download={`${asset.id}.png`}>
              下载原图
            </a>
          )}
        </div>
      </article>
    );
  }
  const settings = (
    <>
      <span className="eyebrow">{steps[step]}</span>
      <h2>
        {step === 0
          ? "从角色开始"
          : step === 1
            ? "确认角色模样"
            : step === 2
              ? "尝试服装方案"
              : step === 3
                ? "挑选姿态"
                : step === 4
                  ? "添加表情"
                  : "整理资产"}
      </h2>
      {step >= 2 && step <= 4 && (() => {
        const image=selectedImage(step===2 ? selection.identity_asset_id : step===3 ? selection.outfit_asset_id : selection.pose_asset_id);
        return image?.width && image.height ? <p className="muted">沿用画布：{image.width} × {image.height}</p> : null;
      })()}
      {step === 0 ? (
        <>
          <p>选择已有角色，或从模板建立新角色。</p>
          <button onClick={() => setDrawer("character")}>浏览角色模板</button>
        </>
      ) : step === 1 ? (
        <>
          <p>基础服装用于确认模样。每次生成三张，选一张继续。</p>
          <label>画布尺寸<Select aria-label="画布尺寸" value={canvasPreset} onValueChange={setCanvasPreset} disabled={busy || !!pending}>
            {canvasPresets.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}
          </Select></label>
          <p className="muted">选定图片后，换装、姿态与表情沿用它的尺寸。较大尺寸需要更多显存与时间。</p>
        </>
      ) : step === 2 ? (
        <>
          <p>可尝试多套服装，每套三张，最终只选一张。</p>
          <div className="outfit-plans">
            {character?.outfits.map((o) => (
              <label key={o.id}>
                <input
                  type="checkbox"
                  checked={outfitIds.includes(o.id)}
                  onChange={() => toggle(o.id, outfitIds, setOutfitIds)}
                />
                {outfitName(o.id)}
              </label>
            ))}
          </div>
          <button onClick={() => setDrawer("outfit")}>
            <Plus size={16} />
            添加服装方案
          </button>
          <details>
            <summary>自定义与修改服装</summary>
            <div className="disclosure-content">
              <button
                onClick={() =>
                  setOutfitForm({ id: crypto.randomUUID(), name: "", tags: "" })
                }
              >
                自定义服装
              </button>
              {character?.outfits.map((o) => (
                <button
                  key={o.id}
                  onClick={() =>
                    setOutfitForm({
                      id: crypto.randomUUID(),
                      name: outfitName(o.id),
                      tags: o.tags.join(", "),
                      parent_id: o.id,
                    })
                  }
                >
                  修改 {outfitName(o.id)}
                </button>
              ))}
            </div>
          </details>
        </>
      ) : step === 3 ? (
        <p>可以生成多个姿态，只选一张进入表情制作。</p>
      ) : step === 4 ? (
        <>
          <p>所有表情都从同一张中性姿态图制作。</p>
          {expressions.map((m) => (
            <label className="mood-choice" key={m.prompt}>
              <input
                type="checkbox"
                checked={chosenMoods.includes(m.prompt)}
                onChange={() => toggle(m.prompt, chosenMoods, setChosenMoods)}
              />
              {m.name}
            </label>
          ))}
          <details>
            <summary>自定义表情</summary>
            <div className="disclosure-content">
              <label>
                自定义表情提示词
                <input
                  value={customMood}
                  onChange={(e) => setCustomMood(e.target.value)}
                />
              </label>
              <button
                disabled={!customMood.trim()}
                onClick={() => {
                  const text = customMood.trim();
                  if (!expressions.some((m) => m.prompt === text)) {
                    setExpressions([
                      ...expressions,
                      { name: text, prompt: text },
                    ]);
                    setChosenMoods([...chosenMoods, text]);
                  }
                  setCustomMood("");
                }}
              >
                添加表情
              </button>
            </div>
          </details>
        </>
      ) : (
        <>
          <a
            href={`/api/production/characters/${encodeURIComponent(active)}/manifest`}
            download="caster-assets.json"
          >
            下载角色清单
          </a>
          <label>
            服装
            <Select
              aria-label="服装筛选"
              value={filter}
              onValueChange={(value) => setFilter(value)}
            >
              <option value="all">全部服装</option>
              {character?.outfits.map((o) => (
                <option key={o.id} value={o.id}>
                  {outfitName(o.id)}
                </option>
              ))}
            </Select>
          </label>
          <label>
            表情
            <Select
              aria-label="表情筛选"
              value={expressionFilter}
              onValueChange={(value) => setExpressionFilter(value)}
            >
              <option value="all">全部表情</option>
              {[
                ...new Set(
                  assets.map((a) => a.spec.expression).filter(Boolean),
                ),
              ].map((v) => (
                <option key={v} value={v}>
                  {expressionName(v)}
                </option>
              ))}
            </Select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={alpha}
              onChange={(e) => setAlpha(e.target.checked)}
            />
            只看透明图片
          </label>
        </>
      )}
      {source && step >= 2 && step <= 4 && (
        <div className="selected-parent">
          <strong>本次使用的图片</strong>
          <img
            loading="lazy"
            decoding="async"
            src={`/api/assets/${encodeURIComponent(source.id)}/thumbnail`}
            alt="当前来源图片"
          />
          <button className="text-button" onClick={() => go(step - 1)}>
            重新选择来源图片
          </button>
        </div>
      )}
    </>
  );
  const activeJobs =
    data?.jobs.filter(
      (j) =>
        !["succeeded", "failed", "cancelled", "needs_correction"].includes(
          j.state,
        ),
    ) || [];
  const tasks = (
    <>
      <h2>制作记录</h2>
      <p>
        {character?.name} · {activeJobs.length} 项进行中
      </p>
      {[...(data?.batches || [])].reverse().map((b) => (
        <details className="batch" key={b.id}>
          <summary>
            {b.request.role === "identity"
              ? "角色"
              : b.request.role === "outfit"
                ? "服装"
                : b.request.role === "pose"
                  ? "姿态"
                  : b.request.role === "matte"
                    ? "透明输出"
                    : "表情"}{" "}
            ·{" "}
            {
              b.job_ids.filter(
                (id) =>
                  data?.jobs.find((j) => j.id === id)?.state === "succeeded",
              ).length
            }
            /{b.job_ids.length} 完成
          </summary>
          <div className="disclosure-content">
            {b.job_ids.some((id) =>
              ["failed", "needs_correction", "cancelled"].includes(
                data?.jobs.find((j) => j.id === id)?.state || "",
              ),
            ) && (
              <button
                disabled={
                  busy ||
                  !online ||
                  !!pending ||
                  b.job_ids.some(
                    (id) =>
                      ![
                        "succeeded",
                        "failed",
                        "needs_correction",
                        "cancelled",
                      ].includes(
                        data?.jobs.find((j) => j.id === id)?.state || "",
                      ),
                  )
                }
                onClick={() =>
                  void submit({
                    ...b.request,
                    expected_revision: selection.revision,
                    idempotency_key: crypto.randomUUID(),
                    retry_of: b.id,
                    candidates: b.request.candidates.filter((_, i) =>
                      ["failed", "needs_correction", "cancelled"].includes(
                        data?.jobs.find((j) => j.id === b.job_ids[i])?.state ||
                          "",
                      ),
                    ),
                  })
                }
              >
                重新提交未完成项
              </button>
            )}
            {b.job_ids.map((id, itemIndex) => {
              const j = data?.jobs.find((j) => j.id === id);
              if (!j) return null;
              const p = productionProgress(j);
              return (
                <article key={id} className="task">
                  <p>
                    {outfitName(j.spec.outfit_id)} ·{" "}
                    {expressionName(j.spec.expression)}
                  </p>
                  <strong>{productionStateNames[j.state]}</strong>
                  {p !== undefined && j.state === "running" && (
                    <progress value={p} max={100} />
                  )}
                  <div className="task-actions">
                    {j.state === "needs_correction" &&
                      b.request.role === "expression" && (
                        <button
                          disabled={
                            busy ||
                            b.source_asset_id !== selection.pose_asset_id
                          }
                          onClick={() =>
                            setCorrection({
                              batch: b,
                              index: itemIndex,
                              region: ["", "", "", ""],
                            })
                          }
                        >
                          修正人脸区域
                        </button>
                      )}
                    {j.state === "queued" && (
                      <button
                        disabled={busy}
                        onClick={() =>
                          void act(async () => {
                            await productionAPI.cancelQueued(j);
                          })
                        }
                      >
                        取消排队
                      </button>
                    )}
                    {j.outputs
                      .filter(
                        (id) =>
                          assets.find((a) => a.id === id)?.role === "original",
                      )
                      .map((id) => (
                        <button
                          key={id}
                          onClick={() =>
                            setLightbox(assets.find((a) => a.id === id)!)
                          }
                        >
                          查看结果
                        </button>
                      ))}
                  </div>
                  {j.error && (
                    <details>
                      <summary>任务详情</summary>
                      <div className="disclosure-content">
                        <p>{jobErrorLabel(j.error)}</p>
                      </div>
                    </details>
                  )}
                </article>
              );
            })}
          </div>
        </details>
      ))}
      {!data?.batches?.length && <p>提交制作后，进度会显示在这里。</p>}
      <details>
        <summary>历史任务 · {data?.jobs.length || 0}</summary>
        <div className="disclosure-content">
          {data?.jobs.map((j) => (
            <div className="task" key={j.id}>
              <span>
                {assetTypeName(j.spec.asset_type)} ·{" "}
                {productionStateNames[j.state]}
              </span>
              {j.outputs
                .filter(
                  (id) => assets.find((a) => a.id === id)?.role === "original",
                )
                .map((id) => (
                  <button
                    key={id}
                    onClick={() =>
                      setLightbox(assets.find((a) => a.id === id)!)
                    }
                  >
                    查看图片
                  </button>
                ))}
            </div>
          ))}
        </div>
      </details>
    </>
  );
  return (
    <div className="live-workbench">
      <header className="topbar">
        <a className="brand" href="/">
          CASTER <small>角色制作手账</small>
        </a>
        <Select
          aria-label="切换角色"
          disabled={busy}
          value={active}
          onValueChange={(value) => {
            setActive(value);
            setStep(0);
          }}
        >
          <option value="">选择角色</option>
          {characters.map((c) => (
            <option value={c.id} key={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
        <button onClick={() => setTasksOpen(true)}>
          <Clock size={18} />
          制作记录{activeJobs.length ? ` · ${activeJobs.length}` : ""}
        </button>
      </header>
      <nav ref={stepsNav} className="steps" aria-label="制作步骤">
        {steps.map((name, n) => (
          <button
            key={name}
            disabled={!canStep(n)}
            className={step === n ? "active" : ""}
            aria-current={step === n ? "step" : undefined}
            onClick={() => go(n)}
          >
            <span className="step-num">{n + 1}</span>
            {name}
          </button>
        ))}
      </nav>
      {error && (
        <div className="live-status" role="status">
          {error}
          <button onClick={() => setRevision((v) => v + 1)}>重新连接</button>
        </div>
      )}
      {connected && !online && (
        <div className="live-status">
          生成服务尚未开启，可以浏览资产和整理角色。
        </div>
      )}
      <div className="mobile-toolbar">
        <button onClick={() => setSettingsOpen(true)}>
          <SlidersHorizontal size={18} />
          编辑设定
        </button>
        <button onClick={() => setTasksOpen(true)}>制作记录</button>
      </div>
      <div
        className={`live-layout ${tasksOpen && wideScreen ? "with-tasks" : ""}`}
      >
        <aside className="settings desktop-settings">{settings}</aside>
        <main>
          <div className="workspace">
            <h1>
              {step === 0
                ? "选择你的角色"
                : step === 1
                  ? "确定角色的模样"
                  : step === 2
                    ? "为角色搭配服装"
                    : step === 3
                      ? "选择想要的姿态"
                      : step === 4
                        ? "为姿态添加表情"
                        : "下载角色资产"}
            </h1>
            {step === 0 ? (
              <>
                <div className="live-character-list">
                  {characters.map((c) => (
                    <button
                      key={c.id}
                      className={active === c.id ? "selected-candidate" : ""}
                      onClick={() => setActive(c.id)}
                    >
                      <strong>{c.name}</strong>
                      <p>{c.fixed_tags.join("、")}</p>
                      <span>{active === c.id ? "当前角色" : "使用角色"}</span>
                    </button>
                  ))}
                </div>
                <details
                  className="live-new-character"
                  open={characterFormOpen}
                  onToggle={(e) => setCharacterFormOpen(e.currentTarget.open)}
                >
                  <summary>创建新角色</summary>
                  <div className="disclosure-content">
                    <button onClick={() => setDrawer("character")}>
                      从模板填写
                    </button>
                    <label>
                      名称
                      <input
                        value={draft.name}
                        onChange={(e) =>
                          setDraft({ ...draft, name: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      外观标签
                      <textarea
                        value={draft.fixed_tags.join(", ")}
                        onChange={(e) =>
                          setDraft({
                            ...draft,
                            fixed_tags: e.target.value.split(","),
                          })
                        }
                      />
                    </label>
                    <button
                      className="primary"
                      disabled={busy || !connected || !draft.name.trim()}
                      onClick={() =>
                        void act(async () => {
                          let saved: ServerCharacter;
                          try {
                            saved = await productionAPI.createCharacter({
                              ...draft,
                              fixed_tags: draft.fixed_tags
                                .map((t) => t.trim())
                                .filter(Boolean),
                            });
                          } catch (e) {
                            if (
                              !(e instanceof ProductionError) ||
                              e.status !== 409
                            )
                              throw e;
                            const rows = await serverLibrary.characters();
                            const found = rows.find((c) => c.id === draft.id);
                            if (!found) throw e;
                            const expected = {
                              ...draft,
                              fixed_tags: draft.fixed_tags
                                .map((t) => t.trim())
                                .filter(Boolean),
                            };
                            if (
                              found.name !== expected.name ||
                              JSON.stringify(found.fixed_tags) !==
                                JSON.stringify(expected.fixed_tags) ||
                              (found.description || "") !==
                                (expected.description || "")
                            )
                              throw new Error(
                                "角色 ID 已存在且内容不同，请重新建立角色。",
                              );
                            saved = found;
                          }
                          setCharacters((rows) => [
                            ...rows.filter((c) => c.id !== saved.id),
                            saved,
                          ]);
                          setActive(saved.id);
                          setDraft(newCharacter());
                          setStep(1);
                        })
                      }
                    >
                      保存角色并继续
                    </button>
                    <details>
                      <summary>保存为个人模板</summary>
                      <div className="disclosure-content">
                        <button
                          disabled={busy || !draft.name.trim()}
                          onClick={() =>
                            void act(async () => {
                              await serverLibrary.import([
                                {
                                  id: crypto.randomUUID(),
                                  kind: "character",
                                  name: draft.name,
                                  tags: draft.fixed_tags
                                    .map((t) => t.trim())
                                    .filter(Boolean),
                                  description: draft.description,
                                  source: "user",
                                },
                              ]);
                              // The drawer revalidates its current page after a template write.
                              setNotice("已保存到我的模板。");
                            })
                          }
                        >
                          保存角色模板
                        </button>
                      </div>
                    </details>
                  </div>
                </details>
              </>
            ) : step <= 3 ? (
              <>
                {step === 2 &&
                  selection.identity_asset_id &&
                  selectedImage(selection.identity_asset_id)?.spec
                    .outfit_id && (
                    <div className="live-original">
                      <p>也可以继续使用角色原图中的服装。</p>
                      {card(selectedImage(selection.identity_asset_id)!, true)}
                    </div>
                  )}
                {step === 3 && (
                  <div className="live-poses">
                    {presets.map((p) => (
                      <label key={`preset-${p.id}`}>
                        <input
                          type="checkbox"
                          aria-label={p.name}
                          checked={poseIds.includes(`preset:${p.id}`)}
                          onChange={() =>
                            toggle(`preset:${p.id}`, poseIds, setPoseIds)
                          }
                        />
                        <img
                          src={`/api${p.preview_url.replace(/width=\d+/, `width=${selectedImage(selection.outfit_asset_id)?.width || 1024}`).replace(/height=\d+/, `height=${selectedImage(selection.outfit_asset_id)?.height || 1536}`)}`}
                          loading="lazy"
                          decoding="async"
                          alt={p.name}
                        />
                        <span>{p.name}</span>
                      </label>
                    ))}
                    {presetError && <p role="status">{presetError}</p>}
                    {!presets.length && !presetError && (
                      <p>正在加载姿态预设…</p>
                    )}
                  </div>
                )}
                {step === 2 ? (
                  character?.outfits.map((o) => {
                    const items = candidates.filter(
                      (a) => a.spec.outfit_id === o.id,
                    );
                    return items.length ? (
                      <section key={o.id}>
                        <h2>{outfitName(o.id)}</h2>
                        <div className="asset-grid">
                          {items.map((a) => card(a, true))}
                        </div>
                      </section>
                    ) : null;
                  })
                ) : (
                  <div className="asset-grid">
                    {candidates.map((a) => card(a, true))}
                  </div>
                )}
                {!candidates.length && (
                  <p className="empty">
                    还没有候选图片。
                    {online
                      ? "选好设定后，点击下方生成。"
                      : "生成服务开启后即可制作。"}
                  </p>
                )}
              </>
            ) : step === 4 ? (
              <div className="live-expression-table">
                <table>
                  <thead>
                    <tr>
                      <th>中性姿态</th>
                      {chosenMoods.map((m) => (
                        <th key={m}>
                          {expressions.find((e) => e.prompt === m)?.name || m}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <th>
                        {source && (
                          <img
                            loading="lazy"
                            decoding="async"
                            src={`/api/assets/${encodeURIComponent(source.id)}/thumbnail`}
                            alt="所选中性姿态"
                          />
                        )}
                      </th>
                      {chosenMoods.map((m) => {
                        const images = candidates.filter(
                          (a) => a.spec.expression === m,
                        );
                        const latest = images.at(-1);
                        const job = data?.jobs.find(
                          (j) =>
                            j.body.reference_asset_id ===
                              selection.pose_asset_id &&
                            j.spec.expression === m &&
                            j.spec.asset_type === "expression",
                        );
                        return (
                          <td key={m}>
                            {latest ? (
                              card(latest)
                            ) : (
                              <span>
                                {job
                                  ? productionStateNames[job.state]
                                  : "尚未制作"}
                              </span>
                            )}
                            {images.length > 1 && (
                              <details>
                                <summary>
                                  历史候选 · {images.length - 1}
                                </summary>
                                <div className="disclosure-content">
                                  {images.slice(0, -1).map((a) => card(a))}
                                </div>
                              </details>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              <div className={`asset-grid ${alpha ? "checker" : ""}`}>
                {assets
                  .filter(
                    (a) =>
                      ["original", "transparent"].includes(a.role) &&
                      successful(a) &&
                      (filter === "all" || a.spec.outfit_id === filter) &&
                      (expressionFilter === "all" ||
                        a.spec.expression === expressionFilter) &&
                      (!alpha || a.role === "transparent"),
                  )
                  .map((a) => card(a))}
              </div>
            )}
          </div>
          <footer className="actionbar">
            <span>
              {step === 0
                ? "选好角色，继续制作"
                : step === 1
                  ? "选一张角色图"
                  : step === 2
                    ? "所有服装候选，只选一张"
                    : step === 3
                      ? "选一张姿态图添加表情"
                      : step === 4
                        ? "每种表情使用同一张姿态"
                        : "原图与透明资产均从服务器下载"}
            </span>
            <div className="button-row">
              {step > 0 && <button onClick={() => go(step - 1)}>返回</button>}
              {step >= 1 && step <= 4 && (
                <button
                  className="primary"
                  disabled={
                    busy ||
                    !connected ||
                    !online ||
                    !!pending ||
                    (step === 2 && !outfitIds.length) ||
                    (step === 3 && !poseIds.length) ||
                    (step === 4 && !chosenMoods.length)
                  }
                  onClick={() => void submit()}
                >
                  {busy
                    ? "正在提交…"
                    : step === 1
                      ? "生成角色候选"
                      : step === 2
                        ? "生成服装候选"
                        : step === 3
                          ? "生成姿态"
                          : "生成表情"}
                </button>
              )}
              {step < 5 && canStep(step + 1) && (
                <button onClick={() => go(step + 1)}>
                  下一步
                  <ArrowRight size={16} />
                </button>
              )}
            </div>
          </footer>
        </main>
        {tasksOpen && wideScreen && (
          <aside className="live-task-sidebar">
            <button className="text-button" onClick={() => setTasksOpen(false)}>
              收起制作记录
            </button>
            {tasks}
          </aside>
        )}
      </div>
      {pending && (
        <div className="live-pending" role="status">
          上次提交的结果尚未确认。
          <button
            disabled={busy || !connected}
            onClick={() => void submit(pending)}
          >
            核对原批次
          </button>
        </div>
      )}
      {notice && (
        <div className="toast" role="status">
          <span>{notice}</span>
          <button aria-label="关闭提示" onClick={() => setNotice("")}>
            <X size={18} />
          </button>
        </div>
      )}
      {tasksOpen && !wideScreen && (
        <Modal title="制作记录" onClose={() => setTasksOpen(false)}>
          {tasks}
        </Modal>
      )}
      {settingsOpen && (
        <Modal title="编辑设定" onClose={() => setSettingsOpen(false)}>
          <div className="settings">{settings}</div>
        </Modal>
      )}
      {drawer && (
        <TemplateDrawer
          remote
          kind={drawer}
          catalog={catalog.filter((t) => t.source !== "user")}
          personal={catalog.filter((t) => t.source === "user")}
          status="服务器模板库"
          onClose={() => setDrawer(null)}
          onApply={(t) => {
            if (drawer === "character") {
              setDraft({
                ...newCharacter(),
                name: t.display?.name || t.name,
                fixed_tags: [t.trigger, ...t.tags].filter(Boolean) as string[],
                description: t.description || "",
              });
              setCharacterFormOpen(true);
              setNotice("模板已填入，请确认并保存角色。");
              setStep(0);
            } else
              setOutfitForm({
                id: crypto.randomUUID(),
                name: t.display?.name || t.name,
                tags: [t.trigger, ...t.tags, t.description]
                  .filter(Boolean)
                  .join(", "),
              });
            setDrawer(null);
          }}
          onImport={async (items) => {
            await serverLibrary.import(items);
            // The drawer revalidates its current page after a template write.
          }}
          onEdit={async (t) => {
            await serverLibrary.edit(t);
            // The drawer revalidates its current page after a template write.
          }}
        />
      )}
      {outfitForm && (
        <Modal
          title={outfitForm.parent_id ? "保存服装新版本" : "添加服装方案"}
          onClose={() => setOutfitForm(null)}
        >
          <label>
            服装名称
            <input
              value={outfitForm.name}
              onChange={(e) =>
                setOutfitForm({ ...outfitForm, name: e.target.value })
              }
            />
          </label>

          <label>
            服装标签
            <textarea
              value={outfitForm.tags}
              onChange={(e) =>
                setOutfitForm({ ...outfitForm, tags: e.target.value })
              }
            />
          </label>
          <button
            className="primary"
            disabled={busy || !outfitForm.name.trim()}
            onClick={() =>
              void act(async () => {
                await productionAPI.createOutfit(active, {
                  ...outfitForm,
                  tags: outfitForm.tags
                    .split(",")
                    .map((t) => t.trim())
                    .filter(Boolean),
                });
                setOutfitIds((ids) => [...ids, outfitForm.id]);
                setOutfitForm(null);
              })
            }
          >
            保存方案
          </button>
          <details>
            <summary>保存为个人模板</summary>
            <div className="disclosure-content">
              <button
                disabled={busy || !outfitForm.name.trim()}
                onClick={() =>
                  void act(async () => {
                    await serverLibrary.import([
                      {
                        id: crypto.randomUUID(),
                        kind: "outfit",
                        name: outfitForm.name,
                        tags: outfitForm.tags
                          .split(",")
                          .map((t) => t.trim())
                          .filter(Boolean),
                        source: "user",
                      },
                    ]);
                    // The drawer revalidates its current page after a template write.
                    setNotice("已保存到我的模板。");
                  })
                }
              >
                保存服装模板
              </button>
            </div>
          </details>
        </Modal>
      )}
      {correction && (
        <Modal title="修正人脸区域" wide onClose={() => setCorrection(null)}>
          <p>
            填写原图中人脸区域的像素坐标，避开手指与其他人物。坐标依次为左、上、右、下。
          </p>
          <img
            className="live-full-image"
            src={productionAssetURL(correction.batch.source_asset_id!)}
            alt="需要指定人脸的原图"
          />
          <div className="live-region">
            {["左 x1", "上 y1", "右 x2", "下 y2"].map((label, i) => (
              <label key={label}>
                {label}
                <input
                  type="number"
                  min="0"
                  value={correction.region[i]}
                  onChange={(e) =>
                    setCorrection({
                      ...correction,
                      region: correction.region.map((v, n) =>
                        n === i ? e.target.value : v,
                      ),
                    })
                  }
                />
              </label>
            ))}
          </div>
          <button
            disabled={
              busy ||
              !online ||
              !!pending ||
              correction.region.some(
                (v) => v.trim() === "" || !Number.isInteger(Number(v)),
              )
            }
            onClick={() =>
              void submit({
                ...correction.batch.request,
                idempotency_key: crypto.randomUUID(),
                expected_revision: selection.revision,
                retry_of: correction.batch.id,
                candidates: [
                  {
                    ...correction.batch.request.candidates[correction.index],
                    face_region: correction.region.map(Number) as [
                      number,
                      number,
                      number,
                      number,
                    ],
                  },
                ],
              }).then((saved) => {
                if (saved) setCorrection(null);
              })
            }
          >
            重新提交修正项
          </button>
        </Modal>
      )}
      {lightbox && (
        <Modal title="查看原图" wide onClose={() => setLightbox(null)}>
          <img
            className="live-full-image"
            src={productionAssetURL(lightbox.id)}
            alt="服务器原图"
          />
          <a
            href={productionAssetURL(lightbox.id)}
            download={`${lightbox.id}.png`}
          >
            <DownloadSimple size={18} />
            下载原图
          </a>
          {step >= 1 &&
            step <= 3 &&
            (candidates.some((a) => a.id === lightbox.id) ||
              (step === 2 && lightbox.id === selection.identity_asset_id)) && (
              <button
                disabled={busy || !connected || selectedId === lightbox.id}
                onClick={() => void choose(lightbox, stage)}
              >
                {selectedId === lightbox.id ? "已选中" : "选用这张图片"}
              </button>
            )}

          {canMatte(lightbox) && (
            <button
              disabled={busy || !online || !!pending}
              onClick={() => void makeTransparent(lightbox)}
            >
              制作透明图片
            </button>
          )}
        </Modal>
      )}
    </div>
  );
}
