import test from "node:test";
import assert from "node:assert/strict";
import { AgentSession } from "./agent/session";
import {
  createAgentAPI,
  buildToolTraces,
  type AgentEvent,
  type AgentWorkbenchContext,
  type ConversationDetail,
} from "./agent";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
const context: AgentWorkbenchContext = {
  character_id: "a",
  character_name: "A",
  stage: "identity",
  selected_asset_ids: {},
  selected_outfit_id: null,
  selection_revision: 0,
  uncommitted_draft: null,
  candidate_set_id: null,
  canvas_preset: null,
  known_character_ids: ["a"],
};
function event(
  seq: number,
  type = "message.delta",
  run_id = "run-new",
): AgentEvent {
  return {
    event_id: `c:${seq}`,
    conversation_id: "c",
    at: 100 - seq,
    type,
    run_id,
    payload: { text: "你好" },
  };
}
function harness(overrides: Partial<ReturnType<typeof createAgentAPI>> = {}) {
  let detail: ConversationDetail = {
    conversation: { id: "c", title: "会话", character_id: "a", updated: 1 },
    messages: [],
    runs: [],
    events: [],
    plans: [],
    workbench_changes: [],
  };
  const streams: {
    receive: (data: string) => void;
    closed: boolean;
    url: string;
  }[] = [];
  const changes: string[] = [];
  const api = {
    ...createAgentAPI((async () => {
      throw new Error("unexpected API request");
    }) as typeof fetch),
    settings: async () => ({
      configured: true,
      has_api_key: true,
      agent_enabled: true,
      base_url: "",
      model: "test",
      provider: "test",
      providers: [],
    }),
    conversations: async () => [detail.conversation],
    conversation: async () => detail,
    rebindConversation: async (_id: string, character_id: string | null) => ({
      ...detail.conversation,
      character_id,
    }),
    ...overrides,
  };
  const session = new AgentSession(
    api,
    (url, receive) => {
      const stream = { url, receive, closed: false };
      streams.push(stream);
      return () => {
        stream.closed = true;
      };
    },
    (id) => changes.push(id),
  );
  session.rebind("a");
  return {
    session,
    streams,
    changes,
    setDetail: (value: Partial<ConversationDetail>) => {
      detail = { ...detail, ...value };
    },
  };
}

test("failed Agent runs reload their durable message and error instead of dropping the user turn", async () => {
  const h = harness({
    send: async () => {
      h.setDetail({
        messages: [{ id: "m", role: "user", content: "hello", created: 1 }],
        events: [event(1, "run.failed")],
      });
      return {
        run_id: "run-new",
        status: "failed",
        error: "provider unavailable",
      };
    },
  });
  await h.session.connect();
  await h.session.send("hello", context);
  const state = h.session.getSnapshot();
  assert.equal(state.detail?.messages[0].content, "hello");
  assert.equal(state.events[0].type, "run.failed");
  assert.equal(state.optimistic, null);
  assert.match(state.notice, /provider unavailable/);
  assert.equal(state.busy, false);
  assert.equal(h.streams[0].closed, true);
  h.session.disconnect();
});

test("stream replay is deduplicated before text and side effects; old runs cannot become stoppable", async () => {
  const sending = deferred<{ run_id: string; status: string }>();
  const h = harness({ send: () => sending.promise });
  h.setDetail({
    events: [event(9, "message.delta", "old")],
    runs: [{ id: "old", status: "completed" }],
  });
  await h.session.connect();
  const finished = h.session.send("hello", context);
  const stream = h.streams[0];
  assert.match(stream.url, /after=c%3A9/);
  stream.receive(JSON.stringify(event(10, "message.delta", "old")));
  assert.equal(h.session.getSnapshot().runId, "");
  stream.receive("bad JSON");
  stream.receive(JSON.stringify({ ...event(11), conversation_id: "other" }));
  stream.receive(JSON.stringify(event(11)));
  stream.receive(JSON.stringify(event(11)));
  assert.equal(h.session.getSnapshot().streamText, "你好");
  assert.deepEqual(
    h.session.getSnapshot().events.map((e) => e.event_id),
    ["c:9", "c:10", "c:11"],
  );
  sending.resolve({ run_id: "run-new", status: "completed" });
  await finished;
  h.session.disconnect();
});

test("same-tick sends are serialized and callbacks queued by a closed stream cannot contaminate the next run", async () => {
  const first = deferred<{ run_id: string; status: string }>();
  const second = deferred<{ run_id: string; status: string }>();
  let calls = 0;
  const h = harness({
    send: () => (++calls === 1 ? first.promise : second.promise),
  });
  await h.session.connect();
  const finished = h.session.send("one", context);
  await h.session.send("duplicate", context);
  assert.equal(calls, 1);
  first.resolve({ run_id: "first", status: "completed" });
  await finished;
  const next = h.session.send("two", context);
  h.streams[0].receive(JSON.stringify(event(1)));
  assert.equal(h.session.getSnapshot().streamText, "");
  h.streams[1].receive(JSON.stringify(event(2)));
  assert.equal(h.session.getSnapshot().streamText, "你好");
  second.resolve({ run_id: "second", status: "completed" });
  await next;
  h.session.disconnect();
});

test("late HTTP completion after reconnect cannot close or overwrite a new panel request", async () => {
  const first = deferred<{ run_id: string; status: string }>();
  const second = deferred<{ run_id: string; status: string }>();
  let calls = 0;
  const h = harness({
    send: () => (++calls === 1 ? first.promise : second.promise),
  });
  await h.session.connect();
  const old = h.session.send("old", context);
  h.session.disconnect();
  await h.session.connect();
  const current = h.session.send("current", context);
  first.resolve({ run_id: "old", status: "completed" });
  await old;
  assert.equal(h.session.getSnapshot().busy, true);
  assert.equal(h.streams[1].closed, false);
  second.resolve({ run_id: "current", status: "completed" });
  await current;
  h.session.disconnect();
});

test("rapid character changes serialize writes and converge to the latest character", async () => {
  const first = deferred<ConversationDetail["conversation"]>();
  const calls: (string | null)[] = [];
  const h = harness({
    rebindConversation: async (_id, character_id) => {
      calls.push(character_id);
      if (calls.length === 1) return first.promise;
      return { id: "c", title: "会话", updated: 1, character_id };
    },
  });
  await h.session.connect();
  h.session.rebind("b");
  h.session.rebind("c");
  h.session.rebind("d");
  assert.deepEqual(calls, ["b"]);
  first.resolve({ id: "c", title: "会话", updated: 1, character_id: "b" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(calls, ["b", "d"]);
  assert.equal(h.session.getSnapshot().detail?.conversation.character_id, "d");
  assert.equal(h.session.getSnapshot().busy, false);
  h.session.disconnect();
});

test("an uncertain send response still reloads the server record", async () => {
  const h = harness({
    send: async () => {
      h.setDetail({
        messages: [{ id: "m", role: "user", content: "sent", created: 1 }],
      });
      throw new TypeError("network disconnected");
    },
  });
  await h.session.connect();
  await h.session.send("sent", context);
  assert.equal(h.session.getSnapshot().detail?.messages.length, 1);
  assert.match(h.session.getSnapshot().notice, /network disconnected/);
  h.session.disconnect();
});

test("tool status follows server sequence when the wall clock moves backwards", () => {
  const started = { ...event(9, "tool.started"), payload: { call_id: "call" } };
  const completed = {
    ...event(10, "tool.completed"),
    payload: { call_id: "call" },
  };
  assert.equal(buildToolTraces([completed, started])[0].status, "completed");
});

test("a rejected send restores text only when the server confirms no new user message", async () => {
  const h = harness({
    send: async () => {
      throw new TypeError("network disconnected");
    },
  });
  h.setDetail({
    messages: [{ id: "previous", role: "user", content: "hello", created: 1 }],
  });
  await h.session.connect();
  assert.equal(await h.session.send("hello", context), "hello");
  assert.equal(h.session.getSnapshot().optimistic, null);
  h.session.disconnect();
});
