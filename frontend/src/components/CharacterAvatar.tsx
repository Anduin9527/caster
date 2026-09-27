import { ImageSquare, ArrowClockwise, Trash } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
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
  const input = useRef<HTMLInputElement>(null);
  async function change(file: File | null) {
    setWorking(true);
    onBusy(true);
    setMessage("");
    try {
      if (file) await validateAvatar(file);
      await saveAvatar(id, file);
      setRevision((value) => value + 1);
    } catch (reason) {
      setMessage((reason as Error).message);
    } finally {
      setWorking(false);
      onBusy(false);
    }
  }
  return (
    <div className="character-avatar-input">
      <div className="avatar-heading">
        头像 / 参考图 <span>可选</span>
      </div>
      <input
        ref={input}
        style={{ display: "none" }}
        aria-label="选择头像图片"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        disabled={disabled || working}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) void change(file);
        }}
      />
      <button
        type="button"
        className={`avatar-upload-card${url ? " has-image" : ""}`}
        disabled={disabled || working}
        onClick={() => input.current?.click()}
        aria-label={url ? "更换图片" : "上传图片"}
        aria-busy={working}
      >
        {url ? (
          <img
            className="character-avatar-preview"
            src={url}
            alt="新角色的头像参考"
          />
        ) : (
          <span className="avatar-upload-icon">
            <ImageSquare size={32} weight="bold" />
          </span>
        )}
        <span className="avatar-upload-caption">
          {url && <ArrowClockwise size={18} weight="bold" />}
          {working ? "保存中…" : url ? "更换图片" : "上传图片"}
        </span>
      </button>
      {url && (
        <button
          type="button"
          className="avatar-remove"
          disabled={disabled || working}
          onClick={() => void change(null)}
        >
          <Trash size={16} weight="bold" /> 移除
        </button>
      )}
      {(message || error) && <p role="alert">{message || error}</p>}
    </div>
  );
}
