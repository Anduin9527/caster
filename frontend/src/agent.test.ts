import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AssistantMarkdown } from "./AssistantMarkdown";
import {
  buildToolTraces,
  createAgentAPI,
  formatAgentError,
  type AgentEvent,
  type AgentWorkbenchContext,
  type GenerationPlan,
  type WorkbenchChange,
} from "./agent";

test("tool lifecycle events form one persistent chronological trace", () => {
  const events: AgentEvent[] = [
    {
      event_id: "e1",
      conversation_id: "c1",
      run_id: "r1",
      type: "tool.started",
      at: 1,
      payload: {
        call_id: "call-1",
        tool: "search_tag_knowledge",
        label: "查询标签知识",
        arguments: { query: "猫耳 异色瞳" },
      },
    },
    {
      event_id: "e2",
      conversation_id: "c1",
      run_id: "r1",
      type: "tool.completed",
      at: 2,
      payload: {
        call_id: "call-1",
        tool: "search_tag_knowledge",
        label: "查询标签知识",
        summary: "找到 2 个候选",
        duration_ms: 8,
        result: { hit_count: 2, top_titles: ["cat_ears", "heterochromia"] },
      },
    },
  ];

  assert.deepEqual(buildToolTraces(events), [
    {
      call_id: "call-1",
      run_id: "r1",
      tool: "search_tag_knowledge",
      label: "查询标签知识",
      status: "completed",
      summary: "找到 2 个候选",
      arguments: { query: "猫耳 异色瞳" },
      result: { hit_count: 2, top_titles: ["cat_ears", "heterochromia"] },
      started_at: 1,
      duration_ms: 8,
    },
  ]);
});

test("framework iteration errors become a user-facing recovery message", () => {
  const message = formatAgentError(
    "WorkflowRuntimeError: Max iterations of 8 reached!",
  );
  assert.doesNotMatch(message, /WorkflowRuntimeError|Max iterations/);
  assert.match(message, /检索步骤过多/);
});

const context: AgentWorkbenchContext = {
  character_id: "角色/一",
  character_name: "测试角色",
  stage: "outfit",
  selected_asset_ids: { identity: "asset-a", outfit: null, pose: null },
  selected_outfit_id: "casual",
  selection_revision: 7,
  uncommitted_draft: null,
  candidate_set_id: null,
  canvas_preset: "1024x1536",
  known_character_ids: ["角色/一"],
};

test("agent adapter carries the exact workbench context and idempotency key", async () => {
  const calls: { url: string; body?: unknown; method?: string }[] = [];
  const api = createAgentAPI((async (url, init) => {
    calls.push({
      url: String(url),
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      method: init?.method,
    });
    return Response.json(
      String(url).endsWith("/settings")
        ? {
            configured: false,
            has_api_key: false,
            agent_enabled: true,
            providers: [],
          }
        : { run_id: "run-1", status: "completed" },
    );
  }) as typeof fetch);

  await api.settings();
  await api.send("conversation/一", "猫耳加异色瞳", context, "request-1");

  assert.equal(calls[0].url, "/api/agent/settings");
  assert.equal(
    calls[1].url,
    "/api/agent/conversations/conversation%2F%E4%B8%80/messages",
  );
  assert.equal(calls[1].method, "POST");
  assert.deepEqual(calls[1].body, {
    text: "猫耳加异色瞳",
    context,
    idempotency_key: "request-1",
  });
});

test("conversation can be rebound without opening a replacement session", async () => {
  const calls: { url: string; body?: unknown; method?: string }[] = [];
  const api = createAgentAPI((async (url, init) => {
    calls.push({
      url: String(url),
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      method: init?.method,
    });
    return Response.json({ id: "conversation-1", character_id: "luo-tianyi" });
  }) as typeof fetch);

  await api.rebindConversation("conversation/1", "luo-tianyi");

  assert.deepEqual(calls[0], {
    url: "/api/agent/conversations/conversation%2F1/character",
    method: "PUT",
    body: { character_id: "luo-tianyi" },
  });
});

test("approval sends the card revision, content hash and observed selection revision", async () => {
  let body: any;
  const api = createAgentAPI((async (_url, init) => {
    body = JSON.parse(String(init?.body));
    return Response.json({ plan: {} });
  }) as typeof fetch);
  const plan = {
    plan_id: "plan-1",
    revision: 3,
    content_hash: "a".repeat(64),
  } as GenerationPlan;

  await api.approve(plan, 9);

  assert.deepEqual(body, {
    revision: 3,
    content_hash: "a".repeat(64),
    selection_revision: 9,
  });
});

test("workbench approval sends only the content-bound card hash", async () => {
  let call: { url: string; body: unknown } | undefined;
  const api = createAgentAPI((async (url, init) => {
    call = { url: String(url), body: JSON.parse(String(init?.body)) };
    return Response.json({});
  }) as typeof fetch);
  const change = {
    change_id: "change/一",
    content_hash: "b".repeat(64),
  } as WorkbenchChange;

  await api.approveWorkbenchChange(change);

  assert.deepEqual(call, {
    url: "/api/agent/workbench-changes/change%2F%E4%B8%80/approve",
    body: { content_hash: "b".repeat(64) },
  });
});

test("agent adapter surfaces backend detail instead of claiming success", async () => {
  const api = createAgentAPI((async () =>
    Response.json(
      { detail: "该对话已有一轮正在运行" },
      { status: 409 },
    )) as typeof fetch);
  await assert.rejects(
    () => api.conversation("busy"),
    /该对话已有一轮正在运行/,
  );
});

test("assistant markdown renders GFM without executing raw HTML", () => {
  const html = renderToStaticMarkup(
    createElement(AssistantMarkdown, {
      content:
        "**候选**\n\n| tag | 证据 |\n|---|---|\n| `cat_ears` | 猫耳 |\n\n<script>alert('x')</script>\n\n[危险链接](javascript:alert(1))\n\n![远程图](https://tracker.invalid/pixel)",
    }),
  );

  assert.match(html, /<strong>候选<\/strong>/);
  assert.match(html, /<table>/);
  assert.match(html, /<code>cat_ears<\/code>/);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /javascript:/);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /\[图片：远程图\]/);
});
