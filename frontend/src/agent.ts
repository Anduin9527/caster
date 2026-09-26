export type AgentProvider = {
  id: string;
  label: string;
  base_url?: string;
  models?: string[];
};

export type AgentSettings = {
  base_url: string;
  model: string;
  provider: string;
  configured: boolean;
  has_api_key: boolean;
  api_key_masked?: string;
  agent_enabled: boolean;
  providers: AgentProvider[];
};

export type AgentWorkbenchContext = {
  character_id: string | null;
  character_name: string;
  stage: "none" | "identity" | "outfit" | "pose" | "expression" | "export";
  selected_asset_ids: Record<string, string | null>;
  selected_outfit_id: string | null;
  selection_revision: number;
  uncommitted_draft: null;
  candidate_set_id: null;
  canvas_preset: string | null;
  known_character_ids: string[];
  interaction_mode?: "guided" | "direct";
};

export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created: number;
  kind?: string;
  run_id?: string;
};

export type RetrievalHit = {
  doc_id: string;
  kind?: "character_template" | "outfit_template" | "tag" | "wiki";
  template_id?: string | null;
  title: string;
  summary: string;
  source: string;
  source_id?: string;
  chunk_id?: string;
  match: "exact" | "alias" | "token" | "semantic" | "none";
  score: number;
  name_only: boolean;
  matched_fields: ("name" | "definition")[];
  name_provenance?: "canonical" | "translated_name" | "wiki_other_name";
  preview_url?: string | null;
};

export type CandidateSet = {
  candidate_set_id: string;
  query: string;
  hits: RetrievalHit[];
};

export type WorkbenchChange = {
  change_id: string;
  conversation_id: string;
  operation: "create_character" | "append_outfit";
  status: "awaiting_approval" | "applied" | "cancelled" | "stale";
  title: string;
  summary: string;
  character_id: string;
  character_name: string;
  focus: "identity" | "outfit";
  character_template_id?: string | null;
  character_template_name: string;
  character_preview_url?: string | null;
  character_tags: string[];
  outfit_template_id?: string | null;
  outfit_template_name: string;
  outfit_preview_url?: string | null;
  outfit_tags: string[];
  outfit_captions: string[];
  excluded_outfit_tags: string[];
  content_hash: string;
  created_at: number;
  applied_at?: number | null;
};

export type RetrievalEnvelope = {
  schema_version: 1;
  result_state: "unavailable" | "candidates" | "empty";
  strategy: string;
  retrieval_role?: "candidate_evidence_only";
  decision_owner?: "llm";
  query_plan: {
    raw_query: string;
    executable_anchor: string;
    intent: string;
    positive_concepts: string[];
    negative_concepts: string[];
    query_variants: string[];
    executed_queries: string[];
    category_routes: string[];
  } | null;
  score_semantics: string;
  abstention: { supported: false; reason: string };
  warnings: { code: string; message: string }[];
  semantic_available: boolean;
  semantic_reason: string;
  negation: { terms: string[]; enforced: boolean };
  hits: RetrievalHit[];
  ambiguous: RetrievalHit[];
};

export type GenerationPlan = {
  plan_id: string;
  revision: number;
  title: string;
  summary: string;
  status:
    | "draft"
    | "awaiting_approval"
    | "queued"
    | "superseded"
    | "cancelled"
    | "stale";
  route: string;
  source_asset_id?: string | null;
  source_selection_revision?: number | null;
  prompt: { positive?: string; negative?: string };
  parameters: {
    width: number;
    height: number;
    seeds: number[];
    steps?: number | null;
    cfg?: number | null;
    denoise?: number | null;
  };
  keep: string[];
  change: string[];
  allow_creative: string[];
  clarify: string[];
  unresolved: string[];
  content_hash: string;
  job_ids: string[];
};

export type AgentEvent = {
  event_id: string;
  conversation_id: string;
  run_id?: string | null;
  type: string;
  at: number;
  payload: Record<string, unknown>;
};

export type AgentConversation = {
  id: string;
  character_id?: string | null;
  title: string;
  updated: number;
};

export type ConversationDetail = {
  conversation: AgentConversation;
  messages: AgentMessage[];
  runs: {
    id: string;
    status: string;
    message_id?: string;
    tool_calls?: number;
    error?: string;
    created?: number;
    updated?: number;
  }[];
  plans: GenerationPlan[];
  workbench_changes: WorkbenchChange[];
  events: AgentEvent[];
};

export type ToolTrace = {
  call_id: string;
  run_id?: string;
  tool: string;
  label: string;
  status: "running" | "completed" | "failed";
  summary: string;
  arguments?: Record<string, unknown>;
  result?: Record<string, unknown>;
  started_at: number;
  duration_ms?: number;
};

export function compareAgentEvents(a: AgentEvent, b: AgentEvent): number {
  const sequence = (event: AgentEvent) => {
    const prefix = event.conversation_id + ":";
    const suffix = event.event_id.startsWith(prefix)
      ? event.event_id.slice(prefix.length)
      : "";
    return /^\d+$/.test(suffix) ? Number(suffix) : NaN;
  };
  // Server sequence is authoritative even when the wall clock moves backwards.
  return sequence(a) - sequence(b) || a.at - b.at;
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

export function buildToolTraces(events: AgentEvent[]): ToolTrace[] {
  const traces = new Map<string, ToolTrace>();
  for (const event of [...events].sort(compareAgentEvents)) {
    if (
      event.type !== "tool.started" &&
      event.type !== "tool.completed" &&
      event.type !== "tool.failed"
    )
      continue;
    const callId = String(event.payload.call_id || "");
    if (!callId) continue;
    const previous = traces.get(callId);
    const status =
      event.type === "tool.started"
        ? "running"
        : event.type === "tool.completed"
          ? "completed"
          : "failed";
    traces.set(callId, {
      call_id: callId,
      run_id: event.run_id || previous?.run_id || undefined,
      tool: String(event.payload.tool || previous?.tool || "tool"),
      label: String(event.payload.label || previous?.label || "调用工具"),
      status,
      summary: String(
        event.payload.summary ||
          previous?.summary ||
          (status === "running" ? "正在执行" : "已完成"),
      ),
      arguments: record(event.payload.arguments) || previous?.arguments,
      result: record(event.payload.result) || previous?.result,
      started_at: previous?.started_at ?? event.at,
      duration_ms:
        typeof event.payload.duration_ms === "number"
          ? event.payload.duration_ms
          : previous?.duration_ms,
    });
  }
  return [...traces.values()].sort((a, b) => a.started_at - b.started_at);
}

export function formatAgentError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error || "");
  if (/max iterations|WorkflowRuntimeError/i.test(message))
    return "检索步骤过多，本轮已停止；工具过程已保留，可调整条件后重试。";
  return message || "助手没有完成这一轮。";
}

export class AgentAPIError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}

export function createAgentAPI(fetcher: typeof fetch = fetch) {
  async function request<T>(
    path: string,
    init?: RequestInit,
    timeout = 20000,
  ): Promise<T> {
    const response = await fetcher("/api/agent" + path, {
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers || {}),
      },
      signal: init?.signal
        ? AbortSignal.any([init.signal, AbortSignal.timeout(timeout)])
        : AbortSignal.timeout(timeout),
      cache: init?.method ? undefined : "no-store",
    });
    if (!response.ok) {
      let detail = "";
      try {
        detail = String((await response.json()).detail || "");
      } catch {
        /* gateway response */
      }
      throw new AgentAPIError(
        detail || "助手请求未完成（" + response.status + "）",
        response.status,
      );
    }
    return response.json();
  }

  return {
    settings: (signal?: AbortSignal) =>
      request<AgentSettings>("/settings", { signal }),
    saveSettings: (body: {
      base_url: string;
      api_key: string;
      model: string;
      provider: string;
      remember: boolean;
      keep_existing_key: boolean;
    }) =>
      request<AgentSettings>("/settings", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    testSettings: () =>
      request<{ ok: boolean; reason?: string; detail?: string }>(
        "/settings/test",
        { method: "POST", body: "{}" },
      ),
    conversations: (characterId?: string, signal?: AbortSignal) =>
      request<AgentConversation[]>(
        "/conversations" +
          (characterId
            ? "?character_id=" + encodeURIComponent(characterId)
            : ""),
        { signal },
      ),
    createConversation: (characterId: string | null) =>
      request<AgentConversation>("/conversations", {
        method: "POST",
        body: JSON.stringify({
          character_id: characterId,
          title: "角色制作助手",
        }),
      }),
    rebindConversation: (id: string, characterId: string | null) =>
      request<AgentConversation>(
        "/conversations/" + encodeURIComponent(id) + "/character",
        {
          method: "PUT",
          body: JSON.stringify({ character_id: characterId }),
        },
      ),
    conversation: (id: string, signal?: AbortSignal) =>
      request<ConversationDetail>("/conversations/" + encodeURIComponent(id), {
        signal,
      }),
    send: (
      id: string,
      text: string,
      context: AgentWorkbenchContext,
      idempotencyKey: string,
    ) =>
      request<{ run_id: string; status: string; error?: string }>(
        "/conversations/" + encodeURIComponent(id) + "/messages",
        {
          method: "POST",
          body: JSON.stringify({
            text,
            context,
            idempotency_key: idempotencyKey,
          }),
        },
        100000,
      ),
    stop: (runId: string) =>
      request("/runs/" + encodeURIComponent(runId) + "/stop", {
        method: "POST",
        body: "{}",
      }),
    approve: (plan: GenerationPlan, selectionRevision: number) =>
      request<{ plan: GenerationPlan }>(
        "/plans/" + encodeURIComponent(plan.plan_id) + "/approve",
        {
          method: "POST",
          body: JSON.stringify({
            revision: plan.revision,
            content_hash: plan.content_hash,
            selection_revision: selectionRevision,
          }),
        },
      ),
    cancel: (planId: string) =>
      request<GenerationPlan>(
        "/plans/" + encodeURIComponent(planId) + "/cancel",
        { method: "POST", body: "{}" },
      ),
    approveWorkbenchChange: (change: WorkbenchChange) =>
      request<WorkbenchChange>(
        "/workbench-changes/" +
          encodeURIComponent(change.change_id) +
          "/approve",
        {
          method: "POST",
          body: JSON.stringify({ content_hash: change.content_hash }),
        },
      ),
    cancelWorkbenchChange: (changeId: string) =>
      request<WorkbenchChange>(
        "/workbench-changes/" + encodeURIComponent(changeId) + "/cancel",
        { method: "POST", body: "{}" },
      ),
    eventURL: (conversationId: string, after = "") =>
      "/api/agent/conversations/" +
      encodeURIComponent(conversationId) +
      "/events" +
      (after ? "?after=" + encodeURIComponent(after) : ""),
  };
}

export const agentAPI = createAgentAPI();
