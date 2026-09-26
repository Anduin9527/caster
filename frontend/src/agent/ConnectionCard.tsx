import { Gear } from "@phosphor-icons/react";
import { useState } from "react";
import { Select } from "../Select";
import { agentAPI, type AgentSettings } from "../agent";

export function ConnectionCard({
  settings,
  onSaved,
  onCancel,
}: {
  settings: AgentSettings;
  onSaved: (settings: AgentSettings, note: string) => void;
  onCancel?: () => void;
}) {
  const [form, setForm] = useState({
    provider: settings.provider || "custom",
    base_url: settings.base_url || "",
    model: settings.model || "",
    api_key: "",
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function save() {
    setBusy(true);
    setMessage("");
    try {
      const saved = await agentAPI.saveSettings({
        ...form,
        remember: true,
        keep_existing_key: settings.has_api_key && !form.api_key,
      });
      onSaved(saved, "模型连接已保存。");
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function test() {
    setBusy(true);
    try {
      const result = await agentAPI.testSettings();
      setMessage(
        result.ok
          ? "连接与工具调用正常。"
          : result.detail || result.reason || "连接失败。",
      );
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="agent-connection-card">
      <div className="agent-card-title">
        <Gear size={20} weight="bold" />
        <div>
          <span className="eyebrow">模型连接</span>
          <h3>
            {settings.configured ? "调整连接" : "先连接一个支持工具调用的模型"}
          </h3>
        </div>
      </div>
      <label>
        提供商
        <Select
          value={form.provider}
          onValueChange={(provider) => {
            const preset = settings.providers.find(
              (item) => item.id === provider,
            );
            setForm({
              ...form,
              provider,
              base_url: preset?.base_url || form.base_url,
            });
          }}
        >
          {settings.providers.map((provider) => (
            <option value={provider.id} key={provider.id}>
              {provider.label}
            </option>
          ))}
        </Select>
      </label>
      <label>
        Base URL
        <input
          value={form.base_url}
          onChange={(event) =>
            setForm({ ...form, base_url: event.target.value })
          }
          placeholder="https://example.com/v1"
        />
      </label>
      <label>
        模型
        <input
          value={form.model}
          onChange={(event) => setForm({ ...form, model: event.target.value })}
          placeholder="支持 function calling 的模型名称"
        />
      </label>
      <label>
        API Key
        <input
          type="password"
          value={form.api_key}
          onChange={(event) =>
            setForm({ ...form, api_key: event.target.value })
          }
          placeholder={
            settings.has_api_key
              ? "已保存 " + (settings.api_key_masked || "密钥") + "，留空则保留"
              : "只保存在本机数据目录"
          }
        />
      </label>
      {message && <p className="agent-connection-note">{message}</p>}
      <div className="button-row">
        <button className="primary" disabled={busy} onClick={() => void save()}>
          保存连接
        </button>
        {settings.configured && (
          <button disabled={busy} onClick={() => void test()}>
            测试连接
          </button>
        )}
        {settings.configured && onCancel && (
          <button disabled={busy} onClick={onCancel}>
            返回对话
          </button>
        )}
      </div>
    </section>
  );
}
