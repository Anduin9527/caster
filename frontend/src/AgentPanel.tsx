import {
  ArrowUp,
  BookOpen,
  CircleNotch,
  Gear,
  PaperPlaneTilt,
  Stop,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { AssistantMarkdown } from "./AssistantMarkdown";
import {
  agentAPI,
  buildToolTraces,
  type AgentWorkbenchContext,
  type CandidateSet,
  type RetrievalEnvelope,
  type ToolTrace,
  type WorkbenchChange,
} from "./agent";
import "./agent.css";

import { ConnectionCard } from "./agent/ConnectionCard";
import { ToolTimeline } from "./agent/ToolTimeline";
import { RetrievalCard, CandidateCard } from "./agent/EvidenceCards";
import { WorkbenchChangeCard, PlanCard } from "./agent/ApprovalCards";

import { AgentSession } from "./agent/session";
import { readPreference, writePreference } from "./storage";
const AGENT_MODE_KEY = "caster-agent-interaction-mode-v1";
type AgentMode = "guided" | "direct";

export function AgentPanel({
  context,
  onClose,
  onWorkbenchChange,
  showHeader = true,
}: {
  context: AgentWorkbenchContext;
  onClose?: () => void;
  onWorkbenchChange?: (
    characterId: string,
    focus: "identity" | "outfit" | "pose" | "expression",
  ) => void;
  showHeader?: boolean;
}) {
  const workbenchListener = useRef(onWorkbenchChange);
  workbenchListener.current = onWorkbenchChange;
  const [session] = useState(
    () =>
      new AgentSession(undefined, undefined, (id, focus) =>
        workbenchListener.current?.(id, focus),
      ),
  );
  const {
    settings,
    detail,
    events,
    optimistic,
    streamText,
    busy,
    runId,
    activity,
    notice,
  } = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const [text, setText] = useState("");
  const [editingConnection, setEditingConnection] = useState(false);
  const [mode, setMode] = useState<AgentMode>(() =>
    readPreference(AGENT_MODE_KEY) === "direct" ? "direct" : "guided",
  );
  const scroll = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void session.connect();
    return session.disconnect;
  }, [session]);
  useEffect(
    () => session.rebind(context.character_id),
    [session, context.character_id],
  );
  useEffect(() => writePreference(AGENT_MODE_KEY, mode), [mode]);
  useEffect(() => {
    scroll.current?.scrollTo({
      top: scroll.current.scrollHeight,
      behavior: "smooth",
    });
  }, [detail?.messages.length, events.length, streamText, optimistic]);

  function send() {
    const content = text.trim();
    if (!content || session.getSnapshot().busy || !settings?.configured) return;
    setText("");
    void session
      .send(content, { ...context, interaction_mode: mode })
      .then((unsent) => {
        if (unsent) setText((current) => current || unsent);
      });
  }

  const retrievals = useMemo(
    () =>
      events
        .filter((event) => event.type === "retrieval.ready")
        .map((event) => ({
          id: event.event_id,
          value: event.payload as unknown as RetrievalEnvelope,
        })),
    [events],
  );
  const candidateSets = useMemo(
    () =>
      events
        .filter((event) => event.type === "candidates.ready")
        .map((event) => ({
          id: event.event_id,
          value: event.payload as unknown as CandidateSet,
        })),
    [events],
  );
  const plans = detail?.plans || [];
  const workbenchChanges = useMemo(() => {
    const values = new Map(
      (detail?.workbench_changes || []).map((change) => [
        change.change_id,
        change,
      ]),
    );
    for (const event of events) {
      if (event.type !== "workbench.change.ready") continue;
      const change = event.payload.change as WorkbenchChange | undefined;
      if (change?.change_id && !values.has(change.change_id))
        values.set(change.change_id, change);
    }
    return [...values.values()].sort((a, b) => a.created_at - b.created_at);
  }, [detail?.workbench_changes, events]);
  const toolTraces = useMemo(() => buildToolTraces(events), [events]);
  const tracesByRun = useMemo(() => {
    const grouped = new Map<string, ToolTrace[]>();
    for (const trace of toolTraces) {
      if (!trace.run_id) continue;
      grouped.set(trace.run_id, [...(grouped.get(trace.run_id) || []), trace]);
    }
    return grouped;
  }, [toolTraces]);
  const runByMessage = useMemo(
    () =>
      new Map(
        (detail?.runs || [])
          .filter((run) => run.message_id)
          .map((run) => [run.message_id as string, run.id]),
      ),
    [detail?.runs],
  );
  const messages = [
    ...(detail?.messages || []),
    ...(optimistic ? [optimistic] : []),
  ];

  return (
    <section className="agent-panel" aria-label="创作助手">
      {showHeader && (
        <header className="agent-panel-header">
          <div>
            <span className="eyebrow">CASTER AGENT</span>
            <h2>创作助手</h2>
          </div>
          <button
            className="icon-button"
            aria-label="收起创作助手"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>
      )}
      <div className="agent-transcript" ref={scroll}>
        {!settings ? (
          <div className="agent-loading">
            <CircleNotch className="spin" size={22} />
            正在连接助手…
          </div>
        ) : !settings.configured || editingConnection ? (
          <ConnectionCard
            settings={settings}
            onCancel={
              settings.configured
                ? () => setEditingConnection(false)
                : undefined
            }
            onSaved={(saved, message) => {
              session.setSettings(saved);
              setEditingConnection(false);
              session.setNotice(message);
            }}
          />
        ) : (
          <>
            <div className="agent-intro">
              <BookOpen size={22} weight="bold" />
              <div>
                <strong>
                  {mode === "guided" ? "分步搭建角色" : "单张创作"}
                </strong>
                <p>
                  {mode === "guided"
                    ? "选角色、搭服装、做姿态和表情，结果会写入可复用工作台。"
                    : "沿用当前角色与选图，整段描述只准备这一张图，不修改角色库。"}
                </p>
                <div
                  className="agent-mode-switch"
                  role="group"
                  aria-label="创作助手模式"
                >
                  <button
                    className={mode === "guided" ? "selected" : ""}
                    disabled={busy}
                    onClick={() => setMode("guided")}
                  >
                    分步制作
                  </button>
                  <button
                    className={mode === "direct" ? "selected" : ""}
                    disabled={busy}
                    onClick={() => setMode("direct")}
                  >
                    单张创作
                  </button>
                </div>
              </div>
              <button
                className="icon-button"
                aria-label="调整模型连接"
                disabled={busy}
                onClick={() => setEditingConnection(true)}
              >
                <Gear size={18} />
              </button>
            </div>
            {messages.map((message) => {
              const messageRunId =
                message.role === "user"
                  ? runByMessage.get(message.id) ||
                    (message.id.startsWith("optimistic-") ? runId : "")
                  : "";
              return (
                <Fragment key={message.id}>
                  <article className={"agent-message " + message.role}>
                    <span>{message.role === "user" ? "你" : "助手"}</span>
                    <AssistantMarkdown content={message.content} />
                  </article>
                  {messageRunId && (
                    <ToolTimeline
                      traces={tracesByRun.get(messageRunId) || []}
                    />
                  )}
                </Fragment>
              );
            })}
            {retrievals.map((retrieval) => (
              <RetrievalCard value={retrieval.value} key={retrieval.id} />
            ))}
            {candidateSets.map((candidate) => (
              <CandidateCard value={candidate.value} key={candidate.id} />
            ))}
            {workbenchChanges.map((change) => (
              <WorkbenchChangeCard
                change={change}
                busy={busy}
                key={change.change_id}
                onApprove={() => void session.applyWorkbenchChange(change)}
                onCancel={() =>
                  void session.update(
                    () => agentAPI.cancelWorkbenchChange(change.change_id),
                    "工作台变更已取消。",
                  )
                }
              />
            ))}
            {plans.map((plan) => (
              <PlanCard
                plan={plan}
                busy={busy}
                key={plan.plan_id + ":" + plan.revision}
                onApprove={() =>
                  void session.update(
                    () => agentAPI.approve(plan, context.selection_revision),
                    "计划已加入制作队列。",
                  )
                }
                onCancel={() =>
                  void session.update(
                    () => agentAPI.cancel(plan.plan_id),
                    "计划已取消。",
                  )
                }
              />
            ))}
            {streamText && (
              <article className="agent-message assistant streaming">
                <span>助手</span>
                <AssistantMarkdown content={streamText} />
              </article>
            )}
            {!messages.length &&
              !retrievals.length &&
              !candidateSets.length &&
              !workbenchChanges.length &&
              !plans.length && (
                <div className="agent-empty-state">
                  <ArrowUp size={26} weight="bold" />
                  <h3>描述你想找的角色、服装或画面</h3>
                  <p>例如：“猫耳加异色瞳，但不要女仆头饰。”</p>
                </div>
              )}
          </>
        )}
      </div>
      {notice && (
        <div className="agent-notice" role="status">
          <WarningCircle size={17} />
          <span>{notice}</span>
          <button aria-label="关闭提示" onClick={() => session.setNotice("")}>
            <X size={15} />
          </button>
        </div>
      )}
      {settings?.configured && !editingConnection && (
        <footer className="agent-composer">
          {busy && (
            <div className="agent-activity" role="status">
              <CircleNotch className="spin" size={17} />
              {activity || "正在检索并整理方案"}
              {runId && (
                <button onClick={() => void session.stop()}>
                  <Stop size={14} weight="fill" />
                  停止
                </button>
              )}
            </div>
          )}
          <textarea
            rows={3}
            value={text}
            disabled={busy}
            placeholder={
              mode === "guided"
                ? "例如：选择洛天依，搭配无头饰的猫耳女仆装…"
                : "描述这一张图的动作、场景、构图和表情…"
            }
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                void send();
              }
            }}
          />
          <div className="agent-composer-bottom">
            <span>Enter 发送 · Shift + Enter 换行</span>
            <button
              className="primary"
              aria-label="发送给创作助手"
              disabled={busy || !text.trim()}
              onClick={() => void send()}
            >
              <PaperPlaneTilt size={18} weight="fill" />
              发送
            </button>
          </div>
        </footer>
      )}
    </section>
  );
}
