import { useEffect, useState } from "react";
import { readAvatar, saveAvatar, validateAvatar } from "../avatarStorage";

function useAvatar(characterId: string, revision = 0) {
  const [url, setURL] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    let objectURL = "";
    setURL("");
    setError("");
    readAvatar(characterId)
      .then((image) => {
        if (!live || !image) return;
        objectURL = URL.createObjectURL(image);
        setURL(objectURL);
      })
      .catch((reason) => {
        if (live) setError((reason as Error).message);
      });
    return () => {
      live = false;
      if (objectURL) URL.revokeObjectURL(objectURL);
    };
  }, [characterId, revision]);
  return { url, error };
}

export function CharacterAvatar({ id, name }: { id: string; name: string }) {
  const { url } = useAvatar(id);
  return url ? (
    <img className="character-avatar" src={url} alt={`${name} · 头像参考`} />
  ) : null;
}

export function CharacterAvatarInput({
  id,
  disabled,
  onBusy,
}: {
  id: string;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
}) {
  const [revision, setRevision] = useState(0);
  const { url, error } = useAvatar(id, revision);
  const [message, setMessage] = useState("");
  const [working, setWorking] = useState(false);
  async function change(file: File | null) {
    setWorking(true);
    onBusy(true);
    setMessage("");
    try {
      if (file) await validateAvatar(file);
      await saveAvatar(id, file);
      setRevision((value) => value + 1);
      setMessage(file ? "参考图已保存在此浏览器。" : "已移除参考图。");
    } catch (reason) {
      setMessage((reason as Error).message);
    } finally {
      setWorking(false);
      onBusy(false);
    }
  }
  return (
    <div className="character-avatar-input">
      <label>
        头像 / 参考图（可选）
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          disabled={disabled || working}
          onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            event.currentTarget.value = "";
            if (file) void change(file);
          }}
        />
      </label>
      {url && (
        <img
          className="character-avatar-preview"
          src={url}
          alt="新角色的头像参考"
        />
      )}
      {url && (
        <button
          type="button"
          disabled={disabled || working}
          onClick={() => void change(null)}
        >
          移除参考图
        </button>
      )}
      <p className="small muted">
        仅用于角色展示，不参与生成或候选选择。图片保存在当前浏览器，
        刷新后保留；清除网站数据或更换网址、浏览器后不会同步。支持
        PNG、JPEG、WebP，最大 10 MiB。
      </p>
      {(message || error || working) && (
        <p role="status">{working ? "正在保存参考图…" : message || error}</p>
      )}
    </div>
  );
}
