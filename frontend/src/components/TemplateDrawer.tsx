import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  DownloadSimple,
  MagnifyingGlass,
  PencilSimple,
  UploadSimple,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Select } from "../Select";
import { templatePreview } from "../templatePreview";
import { downloadJSON as saveJSON } from "../adapter";
import { serverLibrary } from "../library";
import { parseBundle, type Kind, type Template } from "../model";
import { Modal } from "./Modal";
import { Empty } from "./Empty";

function TemplateImage({ template }: { template: Template }) {
  const url = templatePreview(template);
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  if (!url) return <span className="template-image-empty">暂无配套图片</span>;
  if (failed)
    return <span className="template-image-empty">预览图暂时无法加载</span>;
  return (
    <img
      className="template-preview"
      src={url}
      alt={`${template.name} · 上游参考图`}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

export function TemplateDrawer({
  remote = false,
  kind,
  catalog,
  personal,
  status,
  onApply,
  onClose,
  onImport,
  onEdit,
}: {
  remote?: boolean;
  kind: Kind;
  catalog: Template[];
  personal: Template[];
  status: string;
  onApply: (t: Template) => void;
  onClose: () => void;
  onImport: (items: Template[]) => Promise<void>;
  onEdit: (t: Template) => Promise<void>;
}) {
  const [tab, setTab] = useState<"upstream" | "personal">("upstream"),
    [q, setQ] = useState(""),
    [category, setCategory] = useState(""),
    [page, setPage] = useState(0),
    [selected, setSelected] = useState<Template | null>(null),
    [error, setError] = useState(""),
    [editing, setEditing] = useState("");
  const items = (tab === "upstream" ? catalog : personal).filter(
    (t) => t.kind === kind,
  );
  const localCategories = [
    ...new Set(items.flatMap((t) => t.categories || [])),
  ].sort();
  const results = items.filter(
    (t) =>
      (!category || t.categories?.includes(category)) &&
      JSON.stringify(t).toLocaleLowerCase().includes(q.toLocaleLowerCase()),
  );
  const [remotePage, setRemotePage] = useState<{
    items: Template[];
    total: number;
    categories: string[];
    category_labels?: Record<string, string>;
  }>({ items: [], total: 0, categories: [] });
  const [loading, setLoading] = useState(remote);
  const [loadError, setLoadError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!remote) return;
    let live = true;
    const controller = new AbortController();
    setLoading(true);
    setLoadError("");
    const timer = setTimeout(
      () => {
        serverLibrary
          .page(
            {
              kind,
              source: tab === "personal" ? "user" : "upstream",
              q,
              category,
              offset: page * 12,
            },
            controller.signal,
          )
          .then((data) => {
            if (live) setRemotePage(data);
          })
          .catch((e) => {
            if (live) setLoadError(e.message);
          })
          .finally(() => {
            if (live) setLoading(false);
          });
      },
      q ? 250 : 0,
    );
    return () => {
      live = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [remote, kind, tab, q, category, page, refresh]);
  const categories = remote ? remotePage.categories : localCategories;
  const visible = remote
    ? loading || loadError
      ? []
      : remotePage.items
    : results.slice(page * 12, page * 12 + 12);
  const total = remote ? remotePage.total : results.length;
  useEffect(() => setPage(0), [q, category, tab]);
  async function upload(file?: File) {
    if (!file) return;
    try {
      if (file.size > 16 * 1024 * 1024) throw Error("文件不得超过 16 MiB");
      const data = parseBundle(await file.text());
      await onImport(data);
      setRefresh((r) => r + 1);
      setTab("personal");
      setError(`已处理 ${data.length} 个模板；相同条目会跳过。`);
    } catch (e) {
      setError(
        e instanceof SyntaxError
          ? "JSON 格式错误，请检查引号、逗号和括号；未保存任何内容。"
          : (e as Error).message,
      );
    }
  }
  return (
    <Modal
      wide
      title={kind === "character" ? "角色模板图书馆" : "服装模板图书馆"}
      onClose={onClose}
    >
      <div className="template-toolbar">
        <div className="button-row">
          <button
            className={tab === "upstream" ? "selected" : ""}
            onClick={() => {
              setTab("upstream");
              setCategory("");
              setSelected(null);
            }}
          >
            角色与服装
          </button>
          <button
            className={tab === "personal" ? "selected" : ""}
            onClick={() => {
              setTab("personal");
              setCategory("");
              setSelected(null);
            }}
          >
            我的模板
          </button>
        </div>
        <details className="template-manage">
          <summary>管理模板</summary>
          <div className="disclosure-content">
            <label className="file-button">
              <UploadSimple size={16} />
              导入 JSON
              <input
                type="file"
                accept=".json,application/json"
                onChange={(e) => {
                  upload(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
            <button
              onClick={async () => {
                try {
                  const templates = remote
                    ? (await serverLibrary.templates()).filter(
                        (t) => t.source === "user",
                      )
                    : personal;
                  await saveJSON(
                    { schema_version: 1, templates },
                    "caster-personal-templates.json",
                  );
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <DownloadSimple size={16} />
              导出个人库
            </button>
          </div>
        </details>
      </div>
      <details className="template-storage">
        <summary>模板保存位置</summary>
        <div className="disclosure-content">
          <p className="muted small">{status}</p>
        </div>
      </details>
      <div className="template-search">
        <label className="search-field">
          <MagnifyingGlass size={18} />
          <input
            aria-label="搜索模板"
            placeholder="搜索中文 / 英文名称、作品或 Tag…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <Select
          aria-label="模板分类"
          value={category}
          onValueChange={(value) => {
            setCategory(value);
            setPage(0);
          }}
        >
          <option value="">全部分类</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {remotePage.category_labels?.[c]
                ? `${remotePage.category_labels[c]} · ${c}`
                : c}
            </option>
          ))}
        </Select>
      </div>
      {error && (
        <p role="status" className="inline-message">
          {error}
        </p>
      )}
      <p className="small muted">配图来自上游模板库，仅作角色与服装参考。</p>
      {loading && <p role="status">正在加载模板…</p>}
      {loadError && (
        <p role="alert">
          {loadError}{" "}
          <button onClick={() => setRefresh((r) => r + 1)}>重试</button>
        </p>
      )}
      <div className="template-content">
        <div>
          <div className="template-grid">
            {visible.map((t) => (
              <button
                key={t.id}
                className={`template-card ${selected?.id === t.id ? "selected" : ""}`}
                onClick={() => {
                  setSelected(t);
                  setEditing("");
                }}
              >
                <TemplateImage key={t.id} template={t} />
                <span className="eyebrow">
                  {kind === "character" ? "CHARACTER" : "WARDROBE"}
                </span>
                <strong>{t.display?.name || t.name}</strong>
                {t.display?.name && <span>{t.name}</span>}
                <span>
                  {t.categories
                    ?.slice(0, 2)
                    .map((c, i) => t.display?.categories[i] || c)
                    .join(" / ") || "未分类"}
                </span>
                <p>
                  {t.tags
                    .map((tag) =>
                      t.display?.tags[tag]
                        ? `${t.display.tags[tag]} (${tag})`
                        : tag,
                    )
                    .join(", ")}
                </p>
              </button>
            ))}
          </div>
          {!loading && !loadError && !total && (
            <Empty
              title="没有找到模板"
              text="试试其他关键词，或上传自己的模板 JSON。"
            />
          )}
          <div className="pagination">
            <span>
              {total.toLocaleString()} 个结果 · 第 {page + 1} 页
            </span>
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              aria-label="上一页模板"
            >
              <ArrowLeft />
            </button>
            <button
              disabled={loading || (page + 1) * 12 >= total}
              onClick={() => setPage((p) => p + 1)}
              aria-label="下一页模板"
            >
              <ArrowRight />
            </button>
          </div>
        </div>
        <aside className="template-detail">
          {selected ? (
            <>
              <TemplateImage key={selected.id} template={selected} />
              <span className="eyebrow">模板详情</span>
              <h3>{selected.display?.name || selected.name}</h3>
              {selected.display?.name && (
                <p className="small muted">{selected.name}</p>
              )}
              <p className="small">
                {selected.categories
                  ?.map((c, i) =>
                    selected.display?.categories[i]
                      ? `${selected.display.categories[i]} (${c})`
                      : c,
                  )
                  .join(" / ")}
              </p>
              <p className="small muted">
                来源：{selected.source === "user" ? "个人模板" : "上游数据"}
                <br />
                {selected.source_revision?.slice(0, 10)}
              </p>
              <p className="prompt-text">
                {selected.trigger && (
                  <span>
                    {selected.trigger}
                    <br />
                  </span>
                )}
                {selected.tags.map((tag, i) => (
                  <span key={`${i}-${tag}`} className="bilingual-tag">
                    {selected.display?.tags[tag] && (
                      <strong>{selected.display.tags[tag]} · </strong>
                    )}
                    {tag}
                    <br />
                  </span>
                ))}
                {selected.description}
              </p>
              <button className="primary" onClick={() => onApply(selected)}>
                使用这个模板 <ArrowRight size={16} />
              </button>
              {tab === "personal" && (
                <>
                  <button
                    onClick={() =>
                      setEditing(JSON.stringify(selected, null, 2))
                    }
                  >
                    <PencilSimple size={16} />
                    编辑个人模板
                  </button>
                  {editing && (
                    <>
                      <label>
                        模板 JSON
                        <textarea
                          rows={10}
                          value={editing}
                          onChange={(e) => setEditing(e.target.value)}
                        />
                      </label>
                      <button
                        onClick={async () => {
                          try {
                            const [t] = parseBundle(
                              JSON.stringify({
                                schema_version: 1,
                                templates: [JSON.parse(editing)],
                              }),
                            );
                            if (
                              t.id !== selected.id ||
                              t.kind !== selected.kind
                            )
                              throw Error("编辑时不能修改 ID 或类型");
                            await onEdit(t);
                            setRefresh((r) => r + 1);
                            setSelected(t);
                            setEditing("");
                            setError("个人模板已保存。");
                          } catch (e) {
                            setError(
                              e instanceof SyntaxError
                                ? "JSON 格式错误，请检查引号、逗号和括号；未保存任何内容。"
                                : (e as Error).message,
                            );
                          }
                        }}
                      >
                        保存修改
                      </button>
                    </>
                  )}
                </>
              )}
            </>
          ) : (
            <>
              <BookOpen size={34} weight="light" />
              <p>
                选择一张模板卡片，
                <br />
                在这里查看完整提示词。
              </p>
            </>
          )}
        </aside>
      </div>
    </Modal>
  );
}
