import {
  LinkSimple,
  MagnifyingGlass,
  WarningCircle,
} from "@phosphor-icons/react";
import { TemplatePreview } from "./TemplatePreview";
import type { CandidateSet, RetrievalEnvelope } from "../agent";

const intentNames: Record<string, string> = {
  composition: "组合查询",
  visual_concept: "视觉概念",
  wiki_question: "知识问答",
};
export function RetrievalCard({ value }: { value: RetrievalEnvelope }) {
  const plan = value.query_plan;
  return (
    <article className="agent-retrieval-card">
      <div className="agent-card-title">
        <MagnifyingGlass size={19} weight="bold" />
        <div>
          <span className="eyebrow">QWEN RAG</span>
          <h3>{plan?.raw_query || "知识检索"}</h3>
        </div>
        <span className="agent-stamp">
          {intentNames[plan?.intent || ""] || "检索"}
        </span>
      </div>
      {plan && (
        <div className="agent-concepts">
          {plan.positive_concepts.map((concept) => (
            <span className="agent-chip positive" key={"p-" + concept}>
              {concept}
            </span>
          ))}
          {plan.negative_concepts.map((concept) => (
            <span className="agent-chip negative" key={"n-" + concept}>
              用户排除：{concept}
            </span>
          ))}
        </div>
      )}
      {!value.semantic_available ? (
        <div className="agent-warning">
          <WarningCircle size={18} />
          <span>{value.semantic_reason || "语义检索暂不可用"}</span>
        </div>
      ) : value.hits.length ? (
        <ol className="agent-hit-list">
          {value.hits.slice(0, 5).map((hit, index) => (
            <li key={hit.doc_id}>
              <span className="agent-hit-rank">{index + 1}</span>
              <div>
                <div className="agent-hit-heading">
                  <strong>{hit.title}</strong>
                  <span>{hit.match === "exact" ? "精确" : "语义"}</span>
                </div>
                <p>
                  {hit.name_only && !hit.chunk_id
                    ? "只有名称证据，不能作为正文事实。"
                    : hit.summary}
                </p>
                <div className="agent-evidence">
                  {hit.matched_fields.map((field) => (
                    <span key={field}>
                      {field === "name" ? "名称" : "正文"}
                    </span>
                  ))}
                  {hit.name_provenance && <span>{hit.name_provenance}</span>}
                  {hit.source && (
                    <a href={hit.source} target="_blank" rel="noreferrer">
                      <LinkSimple size={13} />
                      来源
                    </a>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="agent-empty">没有找到可以引用的候选。</p>
      )}
      {value.warnings.map((warning) => (
        <div className="agent-warning" key={warning.code}>
          <WarningCircle size={18} />
          <span>{warning.message}</span>
        </div>
      ))}
      <p className="agent-score-note">
        排名分数不是正确概率；当前不能仅凭分数判断“没有答案”。
      </p>
    </article>
  );
}

export function CandidateCard({ value }: { value: CandidateSet }) {
  const templates = value.hits.filter(
    (hit) =>
      hit.kind === "character_template" || hit.kind === "outfit_template",
  );
  if (!templates.length) return null;
  return (
    <article className="agent-candidate-card">
      <div className="agent-card-title">
        <MagnifyingGlass size={19} weight="bold" />
        <div>
          <span className="eyebrow">模板候选</span>
          <h3>{value.query}</h3>
        </div>
        <span className="agent-stamp">{templates.length} 项</span>
      </div>
      <div className="agent-template-grid">
        {templates.slice(0, 6).map((hit) => (
          <div className="agent-template-candidate" key={hit.doc_id}>
            <TemplatePreview src={hit.preview_url} alt={hit.title + "缩略图"} />
            <div>
              <strong>{hit.title}</strong>
              <span>
                {hit.kind === "character_template" ? "角色模板" : "服装模板"}
              </span>
              <p>{hit.summary || "本地模板"}</p>
            </div>
          </div>
        ))}
      </div>
      <p className="agent-score-note">
        图片来自本地模板缓存；没有缓存时只显示文字信息。
      </p>
    </article>
  );
}
