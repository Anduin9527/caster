import {
  agentAPI,
  compareAgentEvents,
  formatAgentError,
  type AgentEvent,
  type AgentMessage,
  type AgentSettings,
  type AgentWorkbenchContext,
  type ConversationDetail,
  type WorkbenchChange,
} from "../agent";
import { readPreference, writePreference } from "../storage";

const ACTIVE_KEY = "caster-agent-active-conversation-v1";
type Focus = "identity" | "outfit" | "pose" | "expression";
type WorkbenchListener = (characterId: string, focus: Focus) => void;
type OpenStream = (url: string, receive: (data: string) => void) => () => void;
type SessionState = {
  settings: AgentSettings | null;
  detail: ConversationDetail | null;
  events: AgentEvent[];
  optimistic: AgentMessage | null;
  streamText: string;
  busy: boolean;
  runId: string;
  activity: string;
  notice: string;
};

const openEvents: OpenStream = (url, receive) => {
  const source = new EventSource(url);
  source.onmessage = (message) => receive(message.data);
  // The POST and subsequent durable reload remain authoritative on disconnect.
  source.onerror = () => source.close();
  return () => source.close();
};

/** Owns one panel's requests and stream, independently of React render timing. */
export class AgentSession {
  private state: SessionState = {
    settings: null,
    detail: null,
    events: [],
    optimistic: null,
    streamText: "",
    busy: true,
    runId: "",
    activity: "",
    notice: "",
  };
  private listeners = new Set<() => void>();
  private epoch = 0;
  private reads: AbortController | null = null;
  private closeStream: (() => void) | null = null;
  private character: { id: string | null } | null = null;

  constructor(
    private readonly api = agentAPI,
    private readonly openStream: OpenStream = openEvents,
    private readonly onWorkbenchChange?: WorkbenchListener,
  ) {}

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private patch(value: Partial<SessionState>) {
    this.state = { ...this.state, ...value };
    this.listeners.forEach((listener) => listener());
  }
  setNotice = (notice: string) => this.patch({ notice });
  setSettings = (settings: AgentSettings) => this.patch({ settings });
  private current(epoch: number) {
    return this.epoch === epoch && !!this.reads;
  }

  async connect() {
    this.disconnect();
    const epoch = this.epoch;
    this.reads = new AbortController();
    const signal = this.reads.signal;
    this.patch({ busy: true, notice: "" });
    try {
      const [settings, conversations] = await Promise.all([
        this.api.settings(signal),
        this.api.conversations(undefined, signal),
      ]);
      if (!this.current(epoch)) return;
      this.patch({ settings });
      const remembered = readPreference(ACTIVE_KEY);
      const selected =
        conversations.find((item) => item.id === remembered) ||
        conversations[0];
      if (selected) await this.reload(selected.id, epoch);
    } catch (error) {
      if (this.current(epoch)) this.setNotice(formatAgentError(error));
    } finally {
      if (this.current(epoch)) {
        this.patch({ busy: false });
        void this.flushCharacter();
      }
    }
  }

  disconnect = () => {
    this.epoch += 1;
    this.reads?.abort();
    this.reads = null;
    this.closeStream?.();
    this.closeStream = null;
    // Closing the panel does not cancel a mutation or an approved GPU job.
  };

  private async reload(id: string, epoch: number) {
    const loaded = await this.api.conversation(id, this.reads?.signal);
    if (!this.current(epoch)) return;
    const events = [...loaded.events].sort(compareAgentEvents);
    this.patch({ detail: loaded, events, optimistic: null });
    writePreference(ACTIVE_KEY, id);
    return loaded;
  }

  rebind = (id: string | null) => {
    this.character = { id };
    void this.flushCharacter();
  };

  private async flushCharacter() {
    const detail = this.state.detail;
    if (
      !this.reads ||
      this.state.busy ||
      !detail ||
      !this.character ||
      (detail.conversation.character_id || null) === this.character.id
    )
      return;
    const epoch = this.epoch;
    const target = this.character;
    this.patch({ busy: true });
    try {
      const conversation = await this.api.rebindConversation(
        detail.conversation.id,
        target.id,
      );
      if (this.current(epoch))
        this.patch({ detail: { ...this.state.detail!, conversation } });
    } catch (error) {
      if (this.current(epoch)) this.setNotice(formatAgentError(error));
    } finally {
      if (this.current(epoch)) {
        this.patch({ busy: false });
        // Serialize writes; only the latest requested character follows this one.
        if (this.character !== target) void this.flushCharacter();
      }
    }
  }

  private begin() {
    if (!this.reads || this.state.busy) return null;
    this.patch({ busy: true, notice: "" });
    return this.epoch;
  }

  private finish(epoch: number) {
    if (!this.current(epoch)) return;
    this.closeStream?.();
    this.closeStream = null;
    this.patch({ busy: false, streamText: "", activity: "", runId: "" });
    void this.flushCharacter();
  }

  private listen(id: string, epoch: number, characterId: string | null) {
    let live = true;
    const seen = new Set(this.state.events.map((event) => event.event_id));
    const previousRuns = new Set(this.state.detail?.runs.map((run) => run.id));
    const after = this.state.events.at(-1)?.event_id || "";
    const close = this.openStream(this.api.eventURL(id, after), (data) => {
      if (!live || !this.current(epoch) || !this.state.busy) return;
      let event: AgentEvent;
      try {
        event = JSON.parse(data);
      } catch {
        return;
      }
      if (
        !event ||
        event.conversation_id !== id ||
        typeof event.event_id !== "string" ||
        !event.payload ||
        seen.has(event.event_id)
      )
        return;
      seen.add(event.event_id);
      const events = [...this.state.events, event].sort(compareAgentEvents);
      this.patch({ events });
      // A reconnect can replay historical frames. They are evidence, not a new reply.
      if (event.run_id && previousRuns.has(event.run_id)) return;
      if (event.run_id) this.patch({ runId: event.run_id });
      if (
        ["activity", "tool.started", "tool.completed", "tool.failed"].includes(
          event.type,
        )
      )
        this.patch({ activity: String(event.payload.summary || "正在处理") });
      if (event.type === "message.delta")
        this.patch({
          streamText: this.state.streamText + String(event.payload.text || ""),
        });
      if (event.type === "run.failed")
        this.setNotice(formatAgentError(event.payload.detail));
      if (
        event.type === "workbench.updated" &&
        this.character?.id === characterId
      ) {
        const target = String(event.payload.character_id || "");
        const focus = String(event.payload.focus || "identity");
        if (
          target &&
          ["identity", "outfit", "pose", "expression"].includes(focus)
        )
          this.onWorkbenchChange?.(target, focus as Focus);
      }
    });
    this.closeStream = () => {
      live = false;
      close();
    };
  }

  async send(content: string, context: AgentWorkbenchContext) {
    if (!content.trim() || !this.state.settings?.configured) return;
    const epoch = this.begin();
    if (epoch === null) return;
    let id = this.state.detail?.conversation.id;
    const previousMessages = new Set(
      this.state.detail?.messages.map((message) => message.id),
    );
    let acknowledged = false;
    let unsent: string | undefined;
    this.patch({
      streamText: "",
      optimistic: {
        id: "optimistic-" + crypto.randomUUID(),
        role: "user",
        content,
        created: Date.now() / 1000,
      },
    });
    try {
      if (!id) {
        const conversation = await this.api.createConversation(
          context.character_id,
        );
        if (!this.current(epoch)) return;
        id = conversation.id;
        writePreference(ACTIVE_KEY, id);
        this.patch({
          detail: {
            conversation,
            messages: [],
            runs: [],
            plans: [],
            workbench_changes: [],
            events: [],
          },
          events: [],
        });
      }
      this.listen(id, epoch, context.character_id);
      const outcome = await this.api.send(
        id,
        content,
        context,
        crypto.randomUUID(),
      );
      acknowledged = true;
      if (outcome.status === "failed")
        throw new Error(outcome.error || "助手没有完成这一轮。");
    } catch (error) {
      if (this.current(epoch)) this.setNotice(formatAgentError(error));
    } finally {
      if (this.current(epoch) && id) {
        try {
          // Failed runs still own a durable user message and diagnostic events.
          const loaded = await this.reload(id, epoch);
          if (
            loaded &&
            !acknowledged &&
            !loaded.messages.some(
              (message) =>
                message.role === "user" &&
                message.content === content &&
                !previousMessages.has(message.id),
            )
          )
            unsent = content;
        } catch (error) {
          if (this.current(epoch))
            this.setNotice(this.state.notice || formatAgentError(error));
        }
      } else if (this.current(epoch) && !id) {
        this.patch({ optimistic: null });
        unsent = content;
      }
      this.finish(epoch);
    }
    // Restore the composer only after a read confirms that the failed request
    // did not add a message. Never automatically resend an uncertain request.
    return this.current(epoch) ? unsent : undefined;
  }

  async update<T>(
    action: () => Promise<T>,
    message: string,
    applied?: (result: T) => void,
  ) {
    const id = this.state.detail?.conversation.id;
    if (!id) return;
    const epoch = this.begin();
    if (epoch === null) return;
    try {
      const result = await action();
      if (!this.current(epoch)) return;
      applied?.(result);
      await this.reload(id, epoch);
      if (this.current(epoch)) this.setNotice(message);
    } catch (error) {
      if (this.current(epoch)) this.setNotice(formatAgentError(error));
    } finally {
      this.finish(epoch);
    }
  }

  applyWorkbenchChange = (change: WorkbenchChange) => {
    const character = this.character;
    return this.update(
      () => this.api.approveWorkbenchChange(change),
      "工作台变更已应用。",
      (applied) => {
        if (character === this.character)
          this.onWorkbenchChange?.(applied.character_id, applied.focus);
      },
    );
  };

  async stop() {
    const { runId } = this.state;
    const epoch = this.epoch;
    if (!runId) return;
    try {
      await this.api.stop(runId);
    } catch (error) {
      if (this.current(epoch)) this.setNotice(formatAgentError(error));
    }
  }
}
