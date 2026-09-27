import { useStepNavigation } from "./useStepNavigation";
import { Modal } from "./components/Modal";
import { Brand } from "./components/Brand";
import { TemplateDrawer } from "./components/TemplateDrawer";
import { Empty } from "./components/Empty";
import { Select } from "./Select";
import { ProductionRecords } from "./ProductionRecords";
import { useEffect, useState, useRef } from "react";
import {
  ArrowRight,
  ArrowLeft,
  Check,
  Plus,
  X,
  BookOpen,
  SlidersHorizontal,
  Clock,
  Images,
  DownloadSimple,
  WarningCircle,
  CheckCircle,
  Circle,
  SpinnerGap,
  Eye,
  Stack,
  WifiSlash,
  Paperclip,
  Person,
  Smiley,
  Sparkle,
  ArrowsOut,
} from "@phosphor-icons/react";
import {
  demoRepository,
  downloadJSON as saveJSON,
  downloadImage,
} from "./adapter";
import {
  steps,
  roleNames,
  stateNames,
  current,
  identityReady,
  selectedOutfit,
  poseReady,
  canStep,
  enqueue,
  reviewAsset,
  cancelJob,
  retryJob,
  importTemplates,
  parseBundle,
  uid,
  draftKey,
  outfitKey,
  type State,
  type Template,
  type Kind,
  type Role,
  type Asset,
  type Enqueue,
} from "./model";
import poseData from "./data/poses.json";
import { serverLibrary, characterDraft, type ServerCharacter } from "./library";
const displayOutfit = (name: string) =>
  name === "casual" ? "日常服装" : name === "navy" ? "深蓝外套" : name;
const reviewNames = {
  pending: "待审阅",
  approved: "已确认",
  rejected: "需修正",
};
function ImageSample({
  src,
  alt,
  className = "",
}: {
  src: string;
  alt: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  return failed ? (
    <div className="missing-image">
      <Images size={32} />
      <span>历史样例文件未准备</span>
    </div>
  ) : (
    <img
      className={className}
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
    />
  );
}
function PoseDrawing({ index }: { index: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, 160, 210);
    const data = poseData.poses[index - 1] as Record<string, number[]>;
    const edges = [
      ["nose", "neck"],
      ["neck", "r_shoulder"],
      ["neck", "l_shoulder"],
      ["r_shoulder", "r_elbow"],
      ["r_elbow", "r_wrist"],
      ["l_shoulder", "l_elbow"],
      ["l_elbow", "l_wrist"],
      ["neck", "r_hip"],
      ["neck", "l_hip"],
      ["r_hip", "l_hip"],
      ["r_hip", "r_knee"],
      ["r_knee", "r_ankle"],
      ["l_hip", "l_knee"],
      ["l_knee", "l_ankle"],
      ["nose", "r_eye"],
      ["nose", "l_eye"],
      ["r_eye", "r_ear"],
      ["l_eye", "l_ear"],
    ];
    const xy = (p: number[]) => [
      (p[0] / 512) * 108 + 26,
      (p[1] / 1536) * 194 + 8,
    ];
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    for (const [a, b] of edges) {
      ctx.strokeStyle = a.startsWith("r_") ? "#269b91" : "#2c2c2c";
      ctx.beginPath();
      ctx.moveTo(...(xy(data[a]) as [number, number]));
      ctx.lineTo(...(xy(data[b]) as [number, number]));
      ctx.stroke();
    }
    for (const p of Object.values(data)) {
      ctx.fillStyle = "#e77368";
      ctx.beginPath();
      ctx.arc(...(xy(p) as [number, number]), 2.6, 0, Math.PI * 2);
      ctx.fill();
    }
  }, [index]);
  return (
    <canvas
      ref={ref}
      width={160}
      height={210}
      role="img"
      aria-label={`VNCCS 二维预设 ${index} 骨架图`}
    />
  );
}
export function App() {
  const [s, setS] = useState<State>(() => demoRepository.load());
  const stepsRef = useStepNavigation(s.step);
  const [catalog, setCatalog] = useState<Template[]>([]);
  const [catalogStatus, setCatalogStatus] = useState("正在连接 服务器模板库…");
  const [libraryMode, setLibraryMode] = useState<"server" | "demo">("server");
  const [serverCharacters, setServerCharacters] = useState<ServerCharacter[]>(
    [],
  );
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [libraryError, setLibraryError] = useState("");
  const [libraryBusy, setLibraryBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [notice, setNotice] = useState("");
  function downloadJSON(data: unknown, name: string) {
    saveJSON(data, name).catch((e) => setNotice(e.message));
  }
  const [drawer, setDrawer] = useState<Kind | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [tasksOpen, setTasksOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(true);
  const [previewInfo, setPreviewInfo] = useState(false);
  const debug = new URLSearchParams(window.location.search).has("debug");
  const [lightbox, setLightbox] = useState<Asset | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [newOutfit, setNewOutfit] = useState(false);
  const [addingOutfitTemplate, setAddingOutfitTemplate] = useState(false);
  const selectionKey = `${s.activeId}/${s.outfitId}`;
  const selection = s.selections?.[selectionKey] || {
    poses: [1, 2, 3],
    moods: ["happy", "surprised", "angry"],
  };
  const { poses, moods } = selection;
  function setPoses(update: number[] | ((value: number[]) => number[])) {
    setS((prev) => {
      const old = prev.selections?.[selectionKey] || selection;
      return {
        ...prev,
        selections: {
          ...prev.selections,
          [selectionKey]: {
            ...old,
            poses: typeof update === "function" ? update(old.poses) : update,
          },
        },
      };
    });
  }
  function setMoods(update: string[] | ((value: string[]) => string[])) {
    setS((prev) => {
      const old = prev.selections?.[selectionKey] || selection;
      return {
        ...prev,
        selections: {
          ...prev.selections,
          [selectionKey]: {
            ...old,
            moods: typeof update === "function" ? update(old.moods) : update,
          },
        },
      };
    });
  }
  const [scenario, setScenario] = useState<Enqueue["scenario"]>("success");
  const [alpha, setAlpha] = useState(false);
  const [filterPose, setFilterPose] = useState("");
  const [filterMood, setFilterMood] = useState("");
  const [filterOutfit, setFilterOutfit] = useState("");
  const { c, o } = current(s);
  const chosenOutfit = selectedOutfit(s, c);
  const outfitPlans = s.outfitPlans?.[c.id] || [c.outfits[0].id];
  const readyIdentity = identityReady(s, c),
    readyOutfit = Boolean(chosenOutfit),
    approvedPoses = poseReady(s, c, o);
  const approvedPoseNumbers = [...new Set(approvedPoses.map((p) => p.pose!))];
  const saveWarning = useRef(false);
  useEffect(() => {
    try {
      demoRepository.save(s);
    } catch {
      if (!saveWarning.current) {
        saveWarning.current = true;
        setNotice("浏览器存储空间不足，本次修改暂未保存。请导出模板备份。");
      }
    }
  }, [s]);
  useEffect(() => {
    const interval = setInterval(
      () => setS((prev) => demoRepository.advance(prev)),
      650,
    );
    return () => clearInterval(interval);
  }, []);
  useEffect(() => {
    let disposed = false;
    setCatalog([]);
    setServerCharacters([]);
    setLibraryError("");
    setLibraryBusy(true);
    setCatalogStatus(
      libraryMode === "server"
        ? "正在连接 服务器模板库…"
        : "正在读取本地模板库…",
    );
    Promise.all([
      libraryMode === "server"
        ? serverLibrary.templates()
        : demoRepository.catalog(),
      libraryMode === "server"
        ? serverLibrary.characters().then((rows) => {
            if (!disposed) setServerCharacters(rows);
            return rows;
          })
        : Promise.resolve([]),
    ])
      .then(([items, characters]) => {
        if (disposed) return;
        setCatalog(items);
        setServerCharacters(characters);
        setCatalogStatus(
          `${libraryMode === "server" ? "服务器实时读取" : "本地模板库"} · ${items.length.toLocaleString()} 个模板 · ${characters.length} 个服务器角色`,
        );
      })
      .catch((e) => {
        if (disposed) return;
        setLibraryError(e.message || "后端连接中断，请检查 SSH 隧道。");
        setCatalogStatus("连接失败，请检查网络后重试");
      })
      .finally(() => {
        if (!disposed) setLibraryBusy(false);
      });
    return () => {
      disposed = true;
    };
  }, [libraryMode, refreshKey]);
  const personalTemplates =
    libraryMode === "server"
      ? catalog.filter((t) => t.source === "user")
      : s.templates;
  async function importLibrary(items: Template[]) {
    if (libraryMode === "server") {
      items = items.map((t) => ({ ...t, source: t.source || "user" }));
      await serverLibrary.import(items);
      setCatalog((prev) => [
        ...prev,
        ...items.filter((t) => !prev.some((old) => old.id === t.id)),
      ]);
    } else setS((prev) => importTemplates(prev, items));
  }
  async function editLibrary(t: Template) {
    if (libraryMode === "server") {
      const saved = await serverLibrary.edit(t);
      setCatalog((prev) => prev.map((old) => (old.id === t.id ? saved : old)));
    } else
      setS((prev) => ({
        ...prev,
        templates: prev.templates.map((old) => (old.id === t.id ? t : old)),
      }));
  }
  function useServerCharacter(source: ServerCharacter) {
    const existing = s.characters.find((ch) => ch.sourceId === source.id);
    const draft = existing || characterDraft(source);
    setS((prev) => ({
      ...prev,
      characters: existing ? prev.characters : [...prev.characters, draft],
      activeId: draft.id,
      outfitId: draft.outfits[0].id,
      step: 0,
    }));
    setLibraryOpen(false);
    setNotice(`已选择 ${source.name}`);
  }

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(timer);
  }, [notice]);
  const characterJobs = s.jobs.filter((j) => j.payload.characterId === c.id);
  const pendingForStep = characterJobs.some((j) =>
    ["queued", "running"].includes(j.state),
  );
  const nextReady =
    s.step === 0
      ? Boolean(c.draft.name.trim() && c.draft.tags.trim())
      : s.step === 4
        ? generationComplete()
        : canStep(s, s.step + 1);
  function generationComplete() {
    return s.assets.some(
      (a) =>
        a.characterId === c.id &&
        a.role === "expression" &&
        a.parentId === approvedPoses[0]?.id,
    );
  }
  function mutate(fn: (p: State) => State, message?: string) {
    setS((prev) => {
      try {
        const next = fn(prev);
        if (message) queueMicrotask(() => setNotice(message));
        return next;
      } catch (e) {
        queueMicrotask(() => setNotice((e as Error).message));
        return prev;
      }
    });
  }
  function patchDraft(key: "name" | "tags" | "description", value: string) {
    mutate((prev) => ({
      ...prev,
      characters: prev.characters.map((ch) =>
        ch.id === c.id ? { ...ch, draft: { ...ch.draft, [key]: value } } : ch,
      ),
    }));
  }
  function patchOutfit(key: "name" | "tags", value: string) {
    mutate((prev) => ({
      ...prev,
      characters: prev.characters.map((ch) =>
        ch.id === c.id
          ? {
              ...ch,
              outfits: ch.outfits.map((out) =>
                out.id === o.id ? { ...out, [key]: value } : out,
              ),
            }
          : ch,
      ),
    }));
  }
  function go(step: number) {
    if (!canStep(s, step)) {
      setNotice(
        step === 2
          ? "请先确认当前身份候选。"
          : step === 3
            ? "请先选定一张服装图片。"
            : "请先选定一张姿态图片。",
      );
      return;
    }
    mutate((p) => ({
      ...p,
      step,
      outfitId:
        step >= 3 && step <= 4 && chosenOutfit
          ? chosenOutfit.outfit.id
          : p.outfitId,
    }));
    setSettingsOpen(false);
  }
  function submit(role: Role) {
    mutate(
      (prev) =>
        enqueue(prev, {
          role,
          poses: role === "expression" ? approvedPoseNumbers : poses,
          moods,
          outfitIds: role === "outfit" ? outfitPlans : undefined,
          count: 3,
          scenario,
        }),
      "正在准备样例预览，可在制作记录中查看进度。",
    );
  }
  function applyTemplate(t: Template) {
    if (t.kind === "outfit" && addingOutfitTemplate) {
      const id = uid();
      mutate((prev) => ({
        ...prev,
        outfitId: id,
        outfitPlans: {
          ...prev.outfitPlans,
          [c.id]: [...(prev.outfitPlans?.[c.id] || [c.outfits[0].id]), id],
        },
        characters: prev.characters.map((ch) =>
          ch.id === c.id
            ? {
                ...ch,
                outfits: [
                  ...ch.outfits,
                  {
                    id,
                    name: t.name,
                    tags: [t.trigger, ...t.tags, t.description]
                      .filter(Boolean)
                      .join(", "),
                  },
                ],
              }
            : ch,
        ),
      }));
      setAddingOutfitTemplate(false);
      setDrawer(null);
      setNotice("已添加服装方案。");
      return;
    }
    if (t.kind === "character") {
      mutate((prev) => ({
        ...prev,
        characters: prev.characters.map((ch) =>
          ch.id === c.id
            ? {
                ...ch,
                draft: {
                  name: t.name,
                  tags: [t.trigger, ...t.tags].filter(Boolean).join(", "),
                  description: t.description || "",
                },
              }
            : ch,
        ),
      }));
    } else {
      mutate((prev) => ({
        ...prev,
        characters: prev.characters.map((ch) =>
          ch.id === c.id
            ? {
                ...ch,
                outfits: ch.outfits.map((out) =>
                  out.id === o.id
                    ? {
                        ...out,
                        name: t.name,
                        tags: [t.trigger, ...t.tags, t.description]
                          .filter(Boolean)
                          .join(", "),
                      }
                    : out,
                ),
              }
            : ch,
        ),
      }));
    }
    setDrawer(null);
    setNotice("模板已填入当前草稿；历史图片与批准记录保持不变。");
  }
  async function saveTemplate(kind: Kind) {
    const t: Template = {
      id: `personal-${uid()}`,
      kind,
      name: kind === "character" ? c.draft.name : o.name,
      tags: [kind === "character" ? c.draft.tags : o.tags],
      description: kind === "character" ? c.draft.description : "",
      categories: ["我的小说"],
      source: "user",
    };
    try {
      parseBundle(JSON.stringify({ schema_version: 1, templates: [t] }));
      await importLibrary([t]);
      setNotice(
        libraryMode === "server"
          ? "已保存到共享模板库。"
          : "已保存到本地模板库。",
      );
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  function addCharacter() {
    const id = uid(),
      outId = uid();
    mutate((prev) => ({
      ...prev,
      activeId: id,
      outfitId: outId,
      step: 0,
      characters: [
        ...prev.characters,
        {
          id,
          draft: { name: "未命名角色", tags: "1girl", description: "" },
          outfits: [
            { id: outId, name: "基础服装", tags: "simple neutral clothing" },
          ],
        },
      ],
    }));
  }
  const generationAssets = s.assets.filter(
    (a) =>
      a.characterId === c.id &&
      (s.step <= 2 || a.outfitId === o.id) &&
      a.role ===
        (["identity", "identity", "outfit", "pose", "expression", "expression"][
          s.step
        ] as Role),
  );
  const activeJobs = s.jobs.filter((j) =>
    ["queued", "running"].includes(j.state),
  ).length;
  const visibleAssets = s.assets.filter(
    (a) =>
      a.characterId === c.id &&
      (!filterOutfit || a.outfitId === filterOutfit) &&
      (!filterPose || String(a.pose) === filterPose) &&
      (!filterMood || a.expression === filterMood),
  );
  function assetCurrent(a: Asset) {
    const outfit = c.outfits.find((x) => x.id === a.outfitId);
    return (
      !!outfit &&
      a.draftKey === draftKey(c) &&
      (a.role === "identity" || a.outfitKey === outfitKey(outfit)) &&
      (a.role === "identity" || a.identityId === c.identityId) &&
      (!["pose", "expression"].includes(a.role) ||
        a.baselineId === chosenOutfit?.asset.id) &&
      (a.role !== "expression" || a.parentId === approvedPoses[0]?.id)
    );
  }
  function approve(a: Asset) {
    mutate((prev) => reviewAsset(prev, a.id, "approved"), "已选用这张图片。");
  }
  const settings = (
    <>
      <div className="panel-heading">
        <span className="eyebrow">{steps[s.step]}</span>
        <button
          className="icon-button mobile-only"
          aria-label="关闭设置"
          onClick={() => setSettingsOpen(false)}
        >
          <X />
        </button>
      </div>
      <h2>
        {s.step === 0
          ? "编辑角色"
          : s.step === 1
            ? "确认角色"
            : s.step === 2
              ? "尝试服装方案"
              : s.step === 3
                ? "挑选角色的动作"
                : s.step === 4
                  ? "让情绪有迹可循"
                  : "收好这次的作品"}
      </h2>
      <p className="muted">
        {s.step === 0
          ? "几句描述，记下故事中的那个人。"
          : s.step === 1
            ? "先确定五官、发型和体型。服装将在下一步统一设计。"
            : s.step === 2
              ? "可以尝试多套服装，每套预览 3 张；最后只选一张继续。"
              : s.step === 3
                ? "先制作中性姿态，再为它添加表情。"
                : s.step === 4
                  ? "每一种表情都从已确认的中性姿态开始。"
                  : "原图、透明图和制作清单，都在这里。"}
      </p>
      {s.step === 0 ? (
        <>
          <label>
            角色名称
            <input
              value={c.draft.name}
              onChange={(e) => patchDraft("name", e.target.value)}
              maxLength={100}
            />
          </label>
          <label>
            外观描述
            <textarea
              rows={3}
              value={c.draft.tags}
              onChange={(e) => patchDraft("tags", e.target.value)}
            />
          </label>
          <details className="optional-settings">
            <summary>更多角色设定</summary>
            <div className="disclosure-content">
              <label>
                角色小传
                <textarea
                  rows={3}
                  value={c.draft.description}
                  placeholder="性格、年龄与背景…"
                  onChange={(e) => patchDraft("description", e.target.value)}
                />
              </label>
              <button
                className="text-button"
                onClick={() => saveTemplate("character")}
              >
                保存为模板
              </button>
              <p className="small muted">保存后可在「我的模板」中重复使用。</p>
            </div>
          </details>
        </>
      ) : null}
      {s.step === 1 && (
        <div className="identity-recipe">
          <strong>{c.draft.name}</strong>
          <p>{c.draft.tags}</p>
          <p className="small muted">每次预览 3 张，选一张作为角色原图。</p>
        </div>
      )}
      {s.step === 2 && (
        <>
          <span className="section-label">要尝试的服装 · 可多选</span>
          <div className="outfit-plans">
            {c.outfits.map((out) => (
              <label key={out.id} className="check-row">
                <input
                  type="checkbox"
                  checked={outfitPlans.includes(out.id)}
                  onChange={() =>
                    setS((prev) => ({
                      ...prev,
                      outfitPlans: {
                        ...prev.outfitPlans,
                        [c.id]: outfitPlans.includes(out.id)
                          ? outfitPlans.filter((id) => id !== out.id)
                          : [...outfitPlans, out.id],
                      },
                    }))
                  }
                />
                {displayOutfit(out.name)}
              </label>
            ))}
          </div>
          <button
            className="library-button"
            onClick={() => {
              setAddingOutfitTemplate(true);
              setDrawer("outfit");
            }}
          >
            <Plus size={17} />
            添加服装方案
          </button>
          <details className="optional-settings">
            <summary>编辑服装方案</summary>
            <div className="disclosure-content">
              <button
                className="text-button"
                onClick={() => setNewOutfit(true)}
              >
                手动添加服装
              </button>
              <label>
                选择要编辑的方案
                <Select
                  value={o.id}
                  onValueChange={(value) =>
                    setS((prev) => ({ ...prev, outfitId: value }))
                  }
                >
                  {c.outfits.map((out) => (
                    <option key={out.id} value={out.id}>
                      {displayOutfit(out.name)}
                    </option>
                  ))}
                </Select>
              </label>
              <button
                onClick={() => {
                  setAddingOutfitTemplate(false);
                  setDrawer("outfit");
                }}
              >
                <BookOpen size={17} />
                替换为模板服装
              </button>
              <label>
                服装名称
                <input
                  value={o.name}
                  onChange={(e) => patchOutfit("name", e.target.value)}
                />
              </label>
              <label>
                服装描述
                <textarea
                  rows={3}
                  value={o.tags}
                  onChange={(e) => patchOutfit("tags", e.target.value)}
                />
              </label>
              <button
                className="text-button"
                onClick={() => saveTemplate("outfit")}
              >
                保存为模板
              </button>
            </div>
          </details>
          <p className="small muted">
            本批次 {outfitPlans.length} 套 × 3 张，共 {outfitPlans.length * 3}{" "}
            张候选。
          </p>
        </>
      )}
      {s.step === 3 && chosenOutfit && (
        <div className="selected-parent">
          <span className="section-label">使用这张服装图</span>
          <ImageSample src={chosenOutfit.asset.image} alt="已选中的服装图片" />
          <strong>{displayOutfit(chosenOutfit.outfit.name)}</strong>
          <button className="text-button" onClick={() => go(2)}>
            重新选择服装图
          </button>
        </div>
      )}
      {s.step === 4 && approvedPoses[0] && (
        <div className="selected-parent">
          <span className="section-label">使用这张姿态图</span>
          <ImageSample src={approvedPoses[0].image} alt="已选中的姿态图片" />
          <strong>姿态 {String(approvedPoses[0].pose).padStart(2, "0")}</strong>
          <button className="text-button" onClick={() => go(3)}>
            重新选择姿态图
          </button>
        </div>
      )}
      {s.step === 3 && (
        <>
          <p className="section-label">已选择 {poses.length} 个预设</p>
          <p className="muted small">
            可以尝试多个姿态，最终只选一张图片添加表情。
          </p>
          <details className="optional-settings">
            <summary>姿态说明</summary>
            <div className="disclosure-content">
              <p className="small muted">
                姿态来自 VNCCS
                二维骨架目录，编号保留原始顺序。图片预览使用已有样例，尚不支持按这些骨架生成新图。
              </p>
              <a
                className="source-link"
                href={poseData.source}
                target="_blank"
                rel="noreferrer"
              >
                查看来源
              </a>
            </div>
          </details>
        </>
      )}
      {s.step === 4 && (
        <>
          <span className="section-label">表情清单</span>
          <div className="mood-picks">
            {s.moods.map((m) => (
              <label className="check-row" key={m.id}>
                <input
                  type="checkbox"
                  checked={moods.includes(m.id)}
                  onChange={() =>
                    setMoods((v) =>
                      v.includes(m.id)
                        ? v.filter((x) => x !== m.id)
                        : [...v, m.id],
                    )
                  }
                />
                {m.name}
              </label>
            ))}
          </div>
          <CustomMood
            onAdd={(name, prompt) => {
              const id = uid();
              mutate((prev) => ({
                ...prev,
                moods: [...prev.moods, { id, name, prompt }],
              }));
              setMoods((v) => [...v, id]);
            }}
          />
          <p className="muted small">
            1 张姿态 × {moods.length} 种表情，共{" "}
            {approvedPoses.length ? moods.length : 0} 张图片。
          </p>
        </>
      )}
      {s.step === 5 && (
        <>
          <label>
            服装筛选
            <Select
              value={filterOutfit}
              onValueChange={(value) => setFilterOutfit(value)}
            >
              <option value="">全部服装</option>
              {c.outfits.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </Select>
          </label>
          <label>
            姿态筛选
            <Select
              value={filterPose}
              onValueChange={(value) => setFilterPose(value)}
            >
              <option value="">全部姿态</option>
              {[1, 2, 3, 4, 5, 6].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </Select>
          </label>
          <label>
            表情筛选
            <Select
              value={filterMood}
              onValueChange={(value) => setFilterMood(value)}
            >
              <option value="">全部表情</option>
              {s.moods.map((x) => (
                <option key={x.id}>{x.name}</option>
              ))}
            </Select>
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={alpha}
              onChange={(e) => setAlpha(e.target.checked)}
            />
            透明棋盘预览
          </label>
          <button
            onClick={() =>
              downloadJSON(
                {
                  demo: true,
                  notice: "演示清单，非本次真实推理结果",
                  character: c,
                  assets: visibleAssets,
                },
                "caster-demo-manifest.json",
              )
            }
          >
            <DownloadSimple size={18} />
            下载制作清单
          </button>
          <p className="muted small">
            无透明样例的图片仍展示原图并注明；不会伪造抠图结果。
          </p>
        </>
      )}
    </>
  );
  function isSelected(a: Asset) {
    return (
      assetCurrent(a) &&
      (a.role === "identity"
        ? c.identityId === a.id
        : a.role === "outfit"
          ? chosenOutfit?.asset.id === a.id
          : a.role === "pose"
            ? approvedPoses[0]?.id === a.id
            : a.review === "approved")
    );
  }
  function renderAsset(a: Asset, compact = false) {
    const historic = !assetCurrent(a);
    return (
      <article
        key={a.id}
        className={`asset-card ${compact ? "compact" : ""} ${isSelected(a) ? "selected-candidate" : ""}`}
      >
        <button
          className={`image-button ${alpha && a.alpha ? "checker" : ""}`}
          aria-label={`查看${a.expression || roleNames[a.role]} · ${displayOutfit(a.outfitName)}`}
          onClick={() => setLightbox(a)}
        >
          <ImageSample
            src={alpha && a.alpha ? a.alpha : a.image}
            alt={`${a.characterName} · ${displayOutfit(a.outfitName)} · ${a.expression || roleNames[a.role]} · 历史示例`}
          />
          <span className="zoom-mark">
            <ArrowsOut size={16} />
          </span>
        </button>
        <div className="asset-caption">
          <div>
            <strong>
              {a.expression ||
                (a.pose
                  ? `预设 ${String(a.pose).padStart(2, "0")}`
                  : roleNames[a.role])}
            </strong>
            <span
              className={`badge ${isSelected(a) ? "teal" : a.review === "rejected" ? "red" : "yellow"}`}
            >
              {isSelected(a) ? (
                <Check size={12} />
              ) : a.review === "rejected" ? (
                <WarningCircle size={12} />
              ) : (
                <Clock size={12} />
              )}{" "}
              {a.role === "expression"
                ? reviewNames[a.review]
                : isSelected(a)
                  ? "已选中"
                  : a.review === "rejected"
                    ? "需调整"
                    : "候选"}
            </span>
          </div>
          <p className="small muted">
            {displayOutfit(a.outfitName)}
            {historic ? " · 历史版本" : ""}
          </p>
          <p className="sample-label">
            {a.role === "outfit" ? "换装样例" : "样例图片"}
          </p>
          {alpha && !a.alpha && (
            <p className="sample-label">无透明样例，显示原图</p>
          )}
          <div className="asset-actions">
            {s.step === 5 ? (
              <button
                className="small-button"
                onClick={() =>
                  downloadImage(
                    alpha && a.alpha ? a.alpha : a.image,
                    `caster-demo-${a.id}${alpha && a.alpha ? "-transparent" : ""}.png`,
                  ).catch((e) => setNotice(e.message))
                }
              >
                <DownloadSimple size={15} />
                下载{alpha && a.alpha ? "透明图" : "原图"}
              </button>
            ) : (
              <>
                {a.role === "expression" ? (
                  <button
                    className="small-button"
                    disabled={historic || a.review === "approved"}
                    onClick={() => approve(a)}
                  >
                    <Check size={15} />
                    {a.review === "approved" ? "已保留" : "保留这张"}
                  </button>
                ) : (
                  <label className="candidate-choice">
                    <input
                      type="radio"
                      name={`selected-${c.id}-${a.role}`}
                      checked={isSelected(a)}
                      disabled={historic}
                      onChange={() => approve(a)}
                    />
                    {isSelected(a) ? "已选中" : "选择这张"}
                  </label>
                )}
              </>
            )}
          </div>
        </div>
      </article>
    );
  }
  const workspace = (
    <>
      <div className="workspace-heading">
        <div>
          <h1>
            {
              [
                "选择你的角色",
                "确定角色的模样",
                "为角色搭配服装",
                "选择想要的姿态",
                "为姿态添加表情",
                "下载角色图片",
              ][s.step]
            }
          </h1>
        </div>
      </div>
      {s.step === 0 && (
        <div className="character-start">
          <p className="step-help">
            选择已有角色，或从模板开始。下一步为角色挑选一个模样。
          </p>
          <div className="character-options" aria-label="选择角色">
            {serverCharacters.map((ch) => (
              <button
                key={ch.id}
                className={`character-option ${c.sourceId === ch.id ? "selected" : ""}`}
                aria-pressed={c.sourceId === ch.id}
                onClick={() => useServerCharacter(ch)}
              >
                <span className="character-avatar">
                  <Person size={32} />
                </span>
                <strong>{ch.name}</strong>
                <span>{ch.outfits.length} 套服装</span>
                <p>{ch.fixed_tags.join(" · ")}</p>
                <span className="card-choice">
                  {c.sourceId === ch.id ? (
                    <>
                      <CheckCircle size={17} />
                      已选择
                    </>
                  ) : (
                    <>
                      选择角色 <ArrowRight size={17} />
                    </>
                  )}
                </span>
              </button>
            ))}
            <button
              className="character-option template-choice"
              onClick={() => setDrawer("character")}
            >
              <span className="character-avatar">
                <BookOpen size={32} />
              </span>
              <strong>从模板开始</strong>
              <span>挑选外观，再加入你的设定</span>
              <span className="card-choice">
                浏览模板 <ArrowRight size={17} />
              </span>
            </button>
            <button
              className="character-option blank-choice"
              onClick={addCharacter}
            >
              <Plus size={26} />
              <strong>自己设定角色</strong>
              <span>从名字与外观开始</span>
            </button>
          </div>
          {libraryBusy && (
            <p role="status" className="small muted">
              正在读取角色库…
            </p>
          )}
          {libraryError && (
            <div role="alert" className="inline-message">
              角色库暂时无法连接，你仍可编辑已有角色。
              <button onClick={() => setRefreshKey((k) => k + 1)}>
                重新连接
              </button>
            </div>
          )}
          <div className="chosen-character">
            <CheckCircle size={22} />
            <div>
              <span className="small muted">当前角色</span>
              <h2>{c.draft.name || "未命名角色"}</h2>
              <p>{c.draft.tags || "请在设定中填写外观描述"}</p>
            </div>
            <button
              className="text-button mobile-only"
              onClick={() => setSettingsOpen(true)}
            >
              编辑设定
            </button>
          </div>
        </div>
      )}
      {s.step === 1 && (
        <>
          <div className="section-head">
            <span>
              身份候选 <small>{generationAssets.length} 张</small>
            </span>
            <span className="muted small">点击图片放大查看，满意后选用。</span>
          </div>
          {generationAssets.length ? (
            <div className="asset-grid">
              {generationAssets.map((a) => renderAsset(a))}
            </div>
          ) : (
            <Empty
              title={pendingForStep ? "正在准备角色图片…" : "还没有角色图片"}
              text={
                pendingForStep
                  ? "请稍候，图片准备好后会出现在这里。"
                  : "点击下方「预览角色」，再选用喜欢的图片。"
              }
            />
          )}
        </>
      )}
      {s.step === 2 && (
        <>
          <p className="step-help">
            所有方案都使用同一张角色原图。比较服装候选，只选一张进入姿态制作。
          </p>
          {s.assets.find((a) => a.id === c.identityId) && (
            <details className="identity-reference">
              <summary>查看角色原图</summary>
              <div className="disclosure-content">
                <ImageSample
                  src={s.assets.find((a) => a.id === c.identityId)!.image}
                  alt="已选定的角色原图"
                />
              </div>
            </details>
          )}
          {c.outfits.map((out) => {
            const results = generationAssets.filter(
              (a) => a.outfitId === out.id,
            );
            if (!outfitPlans.includes(out.id) && !results.length) return null;
            return (
              <section className="outfit-results" key={out.id}>
                <div className="section-head">
                  <span>
                    {displayOutfit(out.name)}{" "}
                    <small>{results.length} 张候选</small>
                  </span>
                  <span className="small muted">
                    {chosenOutfit?.outfit.id === out.id
                      ? "已从此方案选定一张"
                      : "每套可尝试多张"}
                  </span>
                </div>
                {results.length ? (
                  <div className="asset-grid">
                    {results.map((a) => renderAsset(a, true))}
                  </div>
                ) : (
                  <p className="empty-inline">
                    预览后，此方案的 3 张候选会出现在这里。
                  </p>
                )}
              </section>
            );
          })}
          {!outfitPlans.length && !generationAssets.length && (
            <Empty
              title="先添加服装方案"
              text="可以同时尝试多套服装，最后只选一张图片。"
            />
          )}
        </>
      )}
      {s.step === 3 && (
        <>
          <div className="section-head">
            <span>
              姿态小样 <small>VNCCS · 01—06</small>
            </span>
            <span className="muted small">点击多选 · 二维预设</span>
          </div>
          <div className="pose-grid">
            {[1, 2, 3, 4, 5, 6].map((p) => (
              <button
                key={p}
                className={`pose-card ${poses.includes(p) ? "picked" : ""}`}
                onClick={() =>
                  setPoses((v) =>
                    v.includes(p) ? v.filter((x) => x !== p) : [...v, p],
                  )
                }
                aria-pressed={poses.includes(p)}
              >
                <span className="pose-number">
                  {String(p).padStart(2, "0")}
                </span>
                <PoseDrawing index={p} />
                <span>
                  预设 {String(p).padStart(2, "0")}
                  {poses.includes(p) ? (
                    <CheckCircle weight="fill" size={20} />
                  ) : (
                    <Circle size={20} />
                  )}
                </span>
              </button>
            ))}
          </div>
          <div className="section-head">
            <span>
              中性姿态结果 <small>{generationAssets.length} 张</small>
            </span>
            <span className="muted small">只选一张，进入表情制作</span>
          </div>
          {generationAssets.length ? (
            <div className="asset-grid">
              {generationAssets.map((a) => renderAsset(a, true))}
            </div>
          ) : (
            <p className="empty-inline">选好动作后，点击下方「预览姿态」。</p>
          )}
        </>
      )}
      {s.step === 4 && (
        <>
          <div className="section-head">
            <span>表情试镜表</span>
            <span className="muted small">每一格都是独立的制作记录</span>
          </div>
          <div className="matrix-scroll">
            <table className="expression-matrix">
              <thead>
                <tr>
                  <th>中性姿态</th>
                  {s.moods
                    .filter((m) => moods.includes(m.id))
                    .map((m) => (
                      <th key={m.id}>{m.name}</th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {approvedPoseNumbers.map((p) => (
                  <tr key={p}>
                    <th>
                      <PoseDrawing index={p} />
                      <span>预设 {String(p).padStart(2, "0")}</span>
                    </th>
                    {s.moods
                      .filter((m) => moods.includes(m.id))
                      .map((m) => {
                        const a = generationAssets.findLast(
                          (a) =>
                            a.parentId === approvedPoses[0]?.id &&
                            a.pose === p &&
                            a.expression === m.name &&
                            assetCurrent(a),
                        );
                        const job = s.jobs.findLast(
                          (j) =>
                            j.payload.characterId === c.id &&
                            j.payload.outfitId === o.id &&
                            j.payload.parentId === approvedPoses[0]?.id &&
                            j.payload.pose === p &&
                            j.payload.expression === m.name &&
                            j.payload.baselineId === o.baselineId,
                        );
                        return (
                          <td key={m.id}>
                            {a && job && job.state !== "succeeded" && (
                              <p className="matrix-job-state">
                                最新任务：{stateNames[job.state]}
                              </p>
                            )}
                            {a ? (
                              renderAsset(a, true)
                            ) : (
                              <button
                                className="matrix-empty"
                                aria-label={`预览姿态 ${p} 的${m.name}表情`}
                                disabled={
                                  job?.state === "running" ||
                                  job?.state === "queued"
                                }
                                onClick={() =>
                                  mutate(
                                    (prev) =>
                                      enqueue(prev, {
                                        role: "expression",
                                        poses: [p],
                                        moods: [m.id],
                                        scenario: "success",
                                      }),
                                    "正在准备这张表情预览。",
                                  )
                                }
                              >
                                {job?.state === "running" ? (
                                  <SpinnerGap size={26} />
                                ) : job?.state === "failed" ||
                                  job?.state === "needs_correction" ? (
                                  <WarningCircle size={26} />
                                ) : (
                                  <Smiley size={26} />
                                )}
                                <span>
                                  {job ? stateNames[job.state] : "点击预览"}
                                </span>
                              </button>
                            )}
                          </td>
                        );
                      })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!approvedPoseNumbers.length && (
            <Empty
              title="先确认一个中性姿态"
              text="请返回姿态制作，选用一张姿态图片。"
            />
          )}
        </>
      )}
      {s.step === 5 && (
        <>
          <div className="section-head">
            <span>
              我的角色资产 <small>{visibleAssets.length} 张</small>
            </span>
            <span className="muted small">包含历史版本与待审阅候选</span>
          </div>
          {visibleAssets.length ? (
            <div className="asset-grid export-grid">
              {visibleAssets.map((a) => renderAsset(a, true))}
            </div>
          ) : (
            <Empty
              title="这里还没有符合条件的图片"
              text="调整筛选条件，或从身份候选开始制作。"
            />
          )}
        </>
      )}
    </>
  );
  const previewLabels = ["", "预览角色", "预览换装", "预览姿态", "预览表情"];
  const nextLabels = [
    "下一步：确认模样",
    "下一步：搭配服装",
    "下一步：选择姿态",
    "下一步：添加表情",
    "查看并下载图片",
  ];
  const previewDisabled =
    pendingForStep ||
    (s.step === 2 && !outfitPlans.length) ||
    (s.step === 3 && !poses.length) ||
    (s.step === 4 && (!moods.length || !approvedPoses.length));
  const footer = (
    <>
      <div className="next-guidance">
        <strong>
          {
            [
              "选好角色后，继续下一步",
              readyIdentity ? "角色模样已选定" : "选用一张图片，继续搭配服装",
              readyOutfit
                ? `已选定：${displayOutfit(chosenOutfit!.outfit.name)}`
                : "从所有方案中，只选一张服装图",
              approvedPoses.length
                ? `已选定姿态 ${String(approvedPoses[0].pose).padStart(2, "0")}`
                : "只选一张姿态图，继续添加表情",
              "选好表情后，可以下载图片",
              `${visibleAssets.length} 张图片`,
            ][s.step]
          }
        </strong>
        <span>
          {pendingForStep
            ? "正在准备预览…"
            : s.step === 0
              ? "设定会自动保存"
              : ""}
        </span>
      </div>
      <div className="button-row">
        {s.step > 0 && (
          <button className="text-button" onClick={() => go(s.step - 1)}>
            <ArrowLeft size={16} />
            返回
          </button>
        )}
        {s.step >= 1 && s.step <= 4 && (
          <button
            className={nextReady || generationAssets.length ? "" : "primary"}
            disabled={previewDisabled}
            onClick={() =>
              submit(
                ["", "identity", "outfit", "pose", "expression"][
                  s.step
                ] as Role,
              )
            }
          >
            <Sparkle size={18} />
            {pendingForStep
              ? "预览准备中…"
              : nextReady || generationAssets.length
                ? "重新预览"
                : previewLabels[s.step]}
          </button>
        )}
        {s.step < 5 && (s.step === 0 || nextReady) && (
          <button
            className="primary"
            disabled={!nextReady}
            onClick={() => go(s.step + 1)}
          >
            {nextLabels[s.step]}
            <ArrowRight size={17} />
          </button>
        )}
      </div>
    </>
  );
  const tasks = (
    <>
      <div className="tasks-heading">
        <div>
          <Clock size={21} />
          <h2>制作记录</h2>
          <span className="count">{activeJobs}</span>
        </div>
        <button
          className="icon-button"
          aria-label="收起制作记录"
          onClick={() => {
            setCollapsed(true);
            setTasksOpen(false);
          }}
        >
          <X size={18} />
        </button>
      </div>
      {c.sourceId && (
        <ProductionRecords key={c.sourceId} characterId={c.sourceId} />
      )}
      <p className="muted small">{c.draft.name}的本地预览记录</p>
      <div className={`connection ${s.offline ? "offline" : ""}`}>
        {s.offline ? (
          <WifiSlash size={16} />
        ) : (
          <Circle size={12} weight="fill" />
        )}
        {s.offline
          ? "预览已暂停"
          : activeJobs
            ? "正在准备图片预览"
            : "暂无进行中的任务"}
      </div>
      {s.offline && (
        <button onClick={() => mutate((prev) => ({ ...prev, offline: false }))}>
          继续预览
        </button>
      )}
      <div className="task-list">
        {!characterJobs.length ? (
          <div className="empty-tasks">
            <Stack size={42} weight="light" />
            <h3>这里记录每一次尝试</h3>
            <p>
              开始制作后，进度和结果
              <br />
              会出现在这张小纸条上。
            </p>
          </div>
        ) : (
          [...new Set(characterJobs.map((j) => j.batchId))]
            .reverse()
            .map((batch, i) => {
              const jobs = s.jobs.filter((j) => j.batchId === batch);
              return (
                <details className="batch" key={batch} open={i === 0}>
                  <summary>
                    <span>
                      制作批次{" "}
                      {
                        s.jobs.filter((j) => j.batchId === batch)[0].payload
                          .characterName
                      }
                    </span>
                    <small>
                      {jobs.filter((j) => j.state === "succeeded").length}/
                      {jobs.length} 成功
                    </small>
                  </summary>
                  <div className="disclosure-content">
                    {jobs.map((j) => (
                      <article className={`task ${j.state}`} key={j.id}>
                        <div className="task-title">
                          <span>
                            {roleNames[j.payload.role]}
                            {j.payload.pose
                              ? ` · ${String(j.payload.pose).padStart(2, "0")}`
                              : ""}
                            {j.payload.expression
                              ? ` · ${j.payload.expression}`
                              : ""}
                          </span>
                          {j.state === "succeeded" ? (
                            <CheckCircle size={18} />
                          ) : j.state === "failed" ||
                            j.state === "needs_correction" ? (
                            <WarningCircle size={18} />
                          ) : (
                            <Clock size={17} />
                          )}
                        </div>
                        <p>{displayOutfit(j.payload.outfitName)}</p>
                        <div className="task-status">
                          <span>
                            {s.offline &&
                            ["running", "queued"].includes(j.state)
                              ? "等待恢复连接"
                              : stateNames[j.state]}
                          </span>
                          <span>
                            {j.state === "running"
                              ? `${j.progress}%`
                              : j.state === "succeeded"
                                ? reviewNames[
                                    s.assets.find((a) => a.id === j.resultId)
                                      ?.review || "pending"
                                  ]
                                : ""}
                          </span>
                        </div>
                        {j.state === "running" && (
                          <progress
                            max="100"
                            value={j.progress}
                            aria-label="图片预览进度"
                          />
                        )}
                        {j.error && (
                          <p className="task-error">
                            {j.state === "needs_correction"
                              ? "图片需要调整，请检查脸部和遮挡区域。"
                              : "预览准备失败，可以重新尝试。"}
                          </p>
                        )}
                        <div className="task-actions">
                          {j.state === "queued" && (
                            <button
                              onClick={() =>
                                mutate((prev) => cancelJob(prev, j.id))
                              }
                            >
                              取消排队
                            </button>
                          )}
                          {["failed", "needs_correction"].includes(j.state) && (
                            <button
                              onClick={() =>
                                mutate(
                                  (prev) => retryJob(prev, j.id),
                                  "已创建新的重试任务；原失败记录保留。",
                                )
                              }
                            >
                              重新提交
                            </button>
                          )}
                          {j.resultId && (
                            <button
                              onClick={() =>
                                setLightbox(
                                  s.assets.find((a) => a.id === j.resultId)!,
                                )
                              }
                            >
                              查看结果 <ArrowRight size={13} />
                            </button>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                </details>
              );
            })
        )}
      </div>
      {debug && (
        <details className="simulation">
          <summary>
            <SlidersHorizontal size={16} />
            演示情景设置
          </summary>
          <div className="disclosure-content">
            <label>
              下一批模拟结果
              <Select
                value={scenario}
                onValueChange={(value) =>
                  setScenario(value as Enqueue["scenario"])
                }
              >
                <option value="success">全部生成成功</option>
                <option value="mixed">混合：成功／失败／待修正</option>
                <option value="failed">生成失败</option>
                <option value="needs_correction">人脸／遮挡待修正</option>
              </Select>
            </label>
            <button
              onClick={() =>
                mutate((prev) => ({ ...prev, offline: !prev.offline }))
              }
            >
              {s.offline ? "恢复模拟连接" : "模拟连接中断"}
            </button>
          </div>
        </details>
      )}
      <div className="sidebar-foot">
        <Paperclip size={16} />
        <span>进度与记录自动保存</span>
      </div>
    </>
  );
  return (
    <div className={`app ${collapsed ? "tasks-collapsed" : ""}`}>
      <header className="topbar">
        <Brand
          onClick={(e) => {
            e.preventDefault();
            go(0);
          }}
        />
        <div className="header-center">
          <button
            className="text-button notebook-label"
            onClick={() => setLibraryOpen(true)}
          >
            角色库
          </button>
          <Select
            aria-label="切换角色"
            value={c.id}
            onValueChange={(value) => {
              const ch = s.characters.find((x) => x.id === value)!;
              mutate((prev) => ({
                ...prev,
                activeId: ch.id,
                outfitId: ch.outfits[0].id,
                step: 0,
              }));
            }}
          >
            {s.characters.map((ch) => (
              <option key={ch.id} value={ch.id}>
                {ch.draft.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="header-actions">
          <button
            className="preview-label"
            onClick={() => setPreviewInfo(true)}
          >
            <Eye size={16} />
            图片预览
          </button>
          <button
            className="desktop-records"
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((v) => !v)}
          >
            <Clock size={18} />
            制作记录{activeJobs > 0 ? ` · ${activeJobs}` : ""}
          </button>
        </div>
      </header>
      <nav ref={stepsRef} className="steps" aria-label="制作步骤">
        {steps.map((label, i) => {
          return (
            <button
              key={label}
              className={s.step === i ? "active" : ""}
              onClick={() => go(i)}
              aria-current={s.step === i ? "step" : undefined}
              disabled={!canStep(s, i)}
              title={!canStep(s, i) ? "请先完成前一步的图片选择" : undefined}
            >
              <span className="step-num">{i + 1}</span>
              <span>{label}</span>
              {i < 5 && <ArrowRight size={13} className="step-arrow" />}
            </button>
          );
        })}
      </nav>
      <div className="mobile-toolbar">
        <button onClick={() => setSettingsOpen(true)}>
          <SlidersHorizontal size={18} />
          编辑设定
        </button>
        <button
          onClick={() => {
            setCollapsed(false);
            setTasksOpen(true);
          }}
        >
          <Clock size={18} />
          制作记录{activeJobs > 0 ? ` · ${activeJobs}` : ""}
        </button>
      </div>
      <aside className="settings desktop-settings">{settings}</aside>
      <main>
        <div className="workspace">{workspace}</div>
        <footer className="actionbar">{footer}</footer>
      </main>
      <aside className="tasks desktop-tasks">{tasks}</aside>
      {notice && (
        <div className="toast" role="status">
          <Paperclip size={19} />
          <span>{notice}</span>
          <button
            className="icon-button"
            aria-label="关闭提示"
            onClick={() => setNotice("")}
          >
            <X size={18} />
          </button>
        </div>
      )}
      {settingsOpen && (
        <Modal title="编辑设定" onClose={() => setSettingsOpen(false)}>
          <div className="settings">{settings}</div>
        </Modal>
      )}
      {tasksOpen && (
        <Modal title="制作记录" onClose={() => setTasksOpen(false)}>
          <div className="tasks">{tasks}</div>
        </Modal>
      )}
      {drawer && (
        <TemplateDrawer
          kind={drawer}
          catalog={catalog.filter((t) => t.source !== "user")}
          personal={personalTemplates}
          status={`${catalogStatus} · ${libraryMode === "server" ? "导入、保存、编辑将写入服务器模板库" : "个人模板仅保存于本浏览器"}`}
          onApply={applyTemplate}
          onClose={() => setDrawer(null)}
          onImport={importLibrary}
          onEdit={editLibrary}
        />
      )}
      {libraryOpen && (
        <Modal title="角色库" onClose={() => setLibraryOpen(false)}>
          <p>选择角色继续制作，或在模板库中寻找新的灵感。</p>
          <details className="optional-settings">
            <summary>存储与连接</summary>
            <div className="disclosure-content">
              <label>
                数据源
                <Select
                  value={libraryMode}
                  onValueChange={(value) =>
                    setLibraryMode(value as "server" | "demo")
                  }
                >
                  <option value="server">共享角色库</option>
                  <option value="demo">本地模板库</option>
                </Select>
              </label>
              <p role="status">{catalogStatus}</p>
              {libraryError && <p role="alert">{libraryError}</p>}
              <button
                disabled={libraryBusy}
                onClick={() => setRefreshKey((k) => k + 1)}
              >
                {libraryBusy ? "读取中…" : "刷新角色库"}
              </button>
              <button
                className="text-button"
                onClick={() => {
                  setLibraryOpen(false);
                  setConfirmReset(true);
                }}
              >
                清空本地工作记录
              </button>
            </div>
          </details>
          {serverCharacters.map((ch) => (
            <article className="server-character" key={ch.id}>
              <h3>{ch.name}</h3>
              <p>
                {ch.id} · {ch.outfits.length} 套服装
              </p>
              <p>{ch.fixed_tags.join(", ")}</p>
              <button onClick={() => useServerCharacter(ch)}>
                使用 {ch.name}
              </button>
            </article>
          ))}
          <button
            onClick={() => {
              setLibraryOpen(false);
              setDrawer("character");
            }}
          >
            打开角色模板库
          </button>
        </Modal>
      )}
      {previewInfo && (
        <Modal title="关于图片预览" onClose={() => setPreviewInfo(false)}>
          <p>角色和模板库已连接，可以选择、导入和保存模板。</p>
          <p>
            图片生成功能暂未开放。当前使用已有样例预览制作流程，图片不会随描述或服装改变。选择图片只保存在当前工作记录中，不会修改已有作品的批准状态。
          </p>
        </Modal>
      )}
      {lightbox && (
        <Modal
          wide
          title={`${lightbox.characterName} · ${lightbox.expression || roleNames[lightbox.role]}`}
          onClose={() => setLightbox(null)}
        >
          <div className="lightbox">
            <div
              className={
                alpha && lightbox.alpha
                  ? "checker lightbox-image"
                  : "lightbox-image"
              }
            >
              <ImageSample
                src={alpha && lightbox.alpha ? lightbox.alpha : lightbox.image}
                alt="历史样例放大图"
              />
            </div>
            <div>
              <span className="badge yellow">样例图片</span>
              <h3>{displayOutfit(lightbox.outfitName)}</h3>
              <p>{lightbox.source}</p>
              <label className="check-row">
                <input
                  type="checkbox"
                  disabled={!lightbox.alpha}
                  checked={alpha}
                  onChange={(e) => setAlpha(e.target.checked)}
                />
                透明样例
              </label>
              {!lightbox.alpha && (
                <p className="small muted">此示例没有透明版本。</p>
              )}
              <p className="small">
                审阅状态：
                {
                  reviewNames[
                    s.assets.find((a) => a.id === lightbox.id)?.review ||
                      lightbox.review
                  ]
                }
              </p>
              <details className="prompt">
                <summary>图片描述</summary>
                <div className="disclosure-content">
                  <p>{lightbox.prompt}</p>
                </div>
              </details>
              <button
                onClick={() =>
                  downloadImage(
                    alpha && lightbox.alpha ? lightbox.alpha : lightbox.image,
                    `caster-demo-${lightbox.id}.png`,
                  ).catch((e) => setNotice(e.message))
                }
              >
                <DownloadSimple size={18} />
                下载图片
              </button>
              <button
                className="primary"
                disabled={!assetCurrent(lightbox) || isSelected(lightbox)}
                onClick={() => {
                  approve(lightbox);
                  setLightbox(null);
                }}
              >
                <Check size={18} />
                {isSelected(lightbox) ? "已选用" : "选用这张图片"}
              </button>
              <button
                className="text-button"
                onClick={() => {
                  mutate(
                    (prev) => reviewAsset(prev, lightbox.id, "rejected"),
                    "已标记为需要调整。",
                  );
                  setLightbox(null);
                }}
              >
                标记为需要调整
              </button>
            </div>
          </div>
        </Modal>
      )}
      {confirmReset && (
        <Modal
          title="翻开一本新的手账？"
          onClose={() => setConfirmReset(false)}
        >
          <p>
            会清除本机的角色草稿、预览记录和本地模板。共享角色库与已有作品不会受影响。
          </p>
          <div className="button-row">
            <button
              onClick={() =>
                downloadJSON(
                  { schema_version: 1, templates: s.templates },
                  "caster-personal-templates.json",
                )
              }
            >
              备份个人模板
            </button>
            <button
              className="danger"
              onClick={() => {
                setS(demoRepository.reset());
                setConfirmReset(false);
                setNotice("本地记录已清空。");
              }}
            >
              清空本地记录
            </button>
          </div>
        </Modal>
      )}
      {newOutfit && (
        <NewOutfit
          onClose={() => setNewOutfit(false)}
          onAdd={(name, tags) => {
            const id = uid();
            mutate((prev) => ({
              ...prev,
              outfitId: id,
              outfitPlans: {
                ...prev.outfitPlans,
                [c.id]: [
                  ...(prev.outfitPlans?.[c.id] || [c.outfits[0].id]),
                  id,
                ],
              },
              characters: prev.characters.map((ch) =>
                ch.id === c.id
                  ? { ...ch, outfits: [...ch.outfits, { id, name, tags }] }
                  : ch,
              ),
            }));
            setNewOutfit(false);
          }}
        />
      )}
    </div>
  );
}
function CustomMood({
  onAdd,
}: {
  onAdd: (name: string, prompt: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [name, setName] = useState(""),
    [prompt, setPrompt] = useState("");
  return (
    <>
      <button className="text-button" onClick={() => setOpen(!open)}>
        <Plus size={16} />
        自定义表情
      </button>
      {open && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim() && prompt.trim()) {
              onAdd(name.trim(), prompt.trim());
              setName("");
              setPrompt("");
              setOpen(false);
            }
          }}
        >
          <label>
            表情名称
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            表情描述
            <input
              required
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="a shy smile"
            />
          </label>
          <button type="submit">添加表情</button>
        </form>
      )}
    </>
  );
}
function NewOutfit({
  onClose,
  onAdd,
}: {
  onClose: () => void;
  onAdd: (name: string, tags: string) => void;
}) {
  const [name, setName] = useState("旅行 · 深蓝外套"),
    [tags, setTags] = useState("navy blue coat, white blouse, black boots");
  return (
    <Modal title="为角色添加一套服装" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim() && tags.trim()) onAdd(name.trim(), tags.trim());
        }}
      >
        <label>
          服装名称
          <input
            autoFocus
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          服装提示词
          <textarea
            required
            rows={4}
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </label>
        <p className="muted">添加后可以从模板库挑选服装，再预览穿着效果。</p>
        <button type="submit" className="primary">
          <Plus size={18} />
          添加到衣橱
        </button>
      </form>
    </Modal>
  );
}
