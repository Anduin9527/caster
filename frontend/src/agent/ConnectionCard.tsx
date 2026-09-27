import { Gear } from "@phosphor-icons/react";
import { useState } from "react";
import { Select } from "../Select";
import { agentAPI, type AgentSettings } from "../agent";
import {
  connectionForm,
  connectionToRemember,
  connectionURL,
  readConnection,
  rememberConnection,
} from "../connectionStorage";

export function ConnectionCard({
  settings,
  onSaved,
  onCancel,
}: {
  settings: AgentSettings;
  onSaved: (settings: AgentSettings, note: string) => void;
  onCancel?: () => void;
}) {
  const [form, setForm] = useState(() => connectionForm(settings));
  const [rememberBrowser, setRememberBrowser] = useState(true);
  const [hasBrowserCopy, setHasBrowserCopy] = useState(
    () => !!readConnection(),
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function save() {
    setBusy(true);
    setMessage("");
    try {
      const keepKey =
        settings.has_api_key &&
        !form.api_key &&
        connectionURL(settings.base_url || "") === connectionURL(form.base_url);
      if (!form.api_key && !keepKey)
        throw new Error("请填写此服务地址对应的 API Key。");
      const saved = await agentAPI.saveSettings({
        ...form,
        remember: true,
        keep_existing_key: keepKey,
      });
      let note = "模型连接已保存，重新打开当前工作台无需再填写。";
      try {
        const copy = rememberBrowser ? connectionToRemember(form) : null;
        rememberConnection(copy);
        if (copy && !copy.api_key)
          note += "浏览器已记住地址与模型；若要备份密钥，请重新输入一次。";
      } catch {
        note += "但浏览器存储不可用，本次未能更新浏览器副本。";
      }
      onSaved(saved, note);
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
              api_key:
                preset?.base_url &&
                connectionURL(preset.base_url) !== connectionURL(form.base_url)
                  ? ""
                  : form.api_key,
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
            setForm({ ...form, base_url: event.target.value, api_key: "" })
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
              : "填写此服务地址对应的密钥"
          }
        />
      </label>
      <label className="connection-remember">
        <input
          type="checkbox"
          checked={rememberBrowser}
          onChange={(event) => setRememberBrowser(event.target.checked)}
        />
        在此浏览器记住连接（包括密钥）
      </label>
      <p className="small muted">
        保存后，当前后端会持续记住连接。浏览器副本只用于同一网址下自动填入表单，不会自动覆盖另一后端的连接。
      </p>
      {settings.has_api_key && (
        <p className="small">密钥已保存；留空即可继续使用，不必重复输入。</p>
      )}
      {hasBrowserCopy && (
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            try {
              rememberConnection(null);
              setHasBrowserCopy(false);
              setRememberBrowser(false);
              setForm({ ...form, api_key: "" });
              setMessage("已清除此浏览器的连接副本，服务端连接保持不变。");
            } catch {
              setMessage("浏览器存储不可用，未能清除连接副本。");
            }
          }}
        >
          清除浏览器副本
        </button>
      )}
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
