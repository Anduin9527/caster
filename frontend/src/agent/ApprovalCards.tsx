import { TemplatePreview } from "./TemplatePreview";
import {
  BookOpen,
  CheckCircle,
  Sparkle,
  WarningCircle,
} from "@phosphor-icons/react";
import type { GenerationPlan, WorkbenchChange } from "../agent";

const routeNames: Record<string, string> = {
  anima_free: "自由动作与构图",
  anima_text: "文字立绘",
  anima_outfit: "角色换装",
  qwen_pose: "姿态生成",
  local_expression: "局部表情",
  anima_background: "背景生成",
  anima_matte: "透明导出",
};
const statusNames: Record<string, string> = {
  draft: "需要补充",
  awaiting_approval: "等待批准",
  queued: "已加入队列",
  superseded: "已有新版本",
  cancelled: "已取消",
  stale: "来源已变化",
};
function TagList({ values }: { values: string[] }) {
  return (
    <div className="agent-change-tags">
      {values.map((value) => (
        <code key={value}>{value}</code>
      ))}
    </div>
  );
}

export function WorkbenchChangeCard({
  change,
  busy,
  onApprove,
  onCancel,
}: {
  change: WorkbenchChange;
  busy: boolean;
  onApprove: () => void;
  onCancel: () => void;
}) {
  const ready = change.status === "awaiting_approval";
  const labels: Record<WorkbenchChange["status"], string> = {
    awaiting_approval: "等待确认",
    applied: "已应用",
    cancelled: "已取消",
    stale: "已失效",
  };
  return (
    <article className="agent-workbench-change-card">
      <div className="agent-card-title">
        <BookOpen size={20} weight="bold" />
        <div>
          <span className="eyebrow">工作台变更</span>
          <h3>{change.title}</h3>
        </div>
        <span className={"agent-stamp" + (ready ? " ready" : "")}>
          {labels[change.status]}
        </span>
      </div>
      <p>{change.summary}</p>
      {change.character_template_id && (
        <section className="agent-change-template">
          <TemplatePreview
            src={change.character_preview_url}
            alt={change.character_template_name + "角色缩略图"}
          />
          <div>
            <span>角色模板</span>
            <strong>{change.character_template_name}</strong>
            <TagList values={change.character_tags} />
          </div>
        </section>
      )}
      {change.outfit_template_id && (
        <section className="agent-change-template">
          <TemplatePreview
            src={change.outfit_preview_url}
            alt={change.outfit_template_name + "服装缩略图"}
          />
          <div>
            <span>服装模板</span>
            <strong>{change.outfit_template_name}</strong>
            <TagList values={change.outfit_tags} />
            {change.outfit_captions.map((caption) => (
              <p key={caption}>{caption}</p>
            ))}
          </div>
        </section>
      )}
      {change.excluded_outfit_tags.length > 0 && (
        <div className="agent-change-exclusions">
          <strong>明确排除</strong>
          <TagList values={change.excluded_outfit_tags} />
        </div>
      )}
      {ready && (
        <div className="button-row">
          <button className="primary" disabled={busy} onClick={onApprove}>
            <CheckCircle size={18} weight="bold" />
            确认并应用到工作台
          </button>
          <button disabled={busy} onClick={onCancel}>
            取消变更
          </button>
        </div>
      )}
      {change.status === "applied" && (
        <p className="agent-queued">
          <CheckCircle size={17} weight="fill" />
          已写入可复用工作台
        </p>
      )}
    </article>
  );
}

export function PlanCard({
  plan,
  busy,
  onApprove,
  onCancel,
}: {
  plan: GenerationPlan;
  busy: boolean;
  onApprove: () => void;
  onCancel: () => void;
}) {
  const ready = plan.status === "awaiting_approval";
  return (
    <article className="agent-plan-card">
      <div className="agent-card-title">
        <Sparkle size={20} weight="fill" />
        <div>
          <span className="eyebrow">生成计划</span>
          <h3>{plan.title}</h3>
        </div>
        <span className={"agent-stamp" + (ready ? " ready" : "")}>
          {statusNames[plan.status] || plan.status}
        </span>
      </div>
      <p>{plan.summary}</p>
      <dl className="agent-plan-facts">
        <div>
          <dt>路线</dt>
          <dd>{routeNames[plan.route] || plan.route}</dd>
        </div>
        <div>
          <dt>画布</dt>
          <dd>
            {plan.parameters.width} × {plan.parameters.height}
          </dd>
        </div>
        <div>
          <dt>候选</dt>
          <dd>{plan.parameters.seeds.length} 张</dd>
        </div>
      </dl>
      {(plan.unresolved.length > 0 || plan.clarify.length > 0) && (
        <div className="agent-warning">
          <WarningCircle size={18} />
          <span>{[...plan.unresolved, ...plan.clarify].join("；")}</span>
        </div>
      )}
      <details>
        <summary>查看将要执行的内容</summary>
        <div className="disclosure-content agent-plan-detail">
          {plan.change.length > 0 && (
            <p>
              <strong>改变：</strong>
              {plan.change.join("、")}
            </p>
          )}
          {plan.keep.length > 0 && (
            <p>
              <strong>保留：</strong>
              {plan.keep.join("、")}
            </p>
          )}
          <p className="agent-prompt-text">
            {plan.prompt.positive || "计划未提供正向提示词"}
          </p>
        </div>
      </details>
      {ready && (
        <div className="button-row">
          <button className="primary" disabled={busy} onClick={onApprove}>
            <CheckCircle size={18} weight="bold" />
            批准并加入队列
          </button>
          <button disabled={busy} onClick={onCancel}>
            取消计划
          </button>
        </div>
      )}
      {plan.status === "queued" && plan.job_ids.length > 0 && (
        <p className="agent-queued">
          <CheckCircle size={17} weight="fill" />
          已提交 {plan.job_ids.length} 项任务
        </p>
      )}
    </article>
  );
}
