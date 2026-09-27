const DATABASE = "caster-local-media-v1";
const STORE = "character-avatars";

async function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    let blocked = false;
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onerror = () =>
      reject(new Error("浏览器图片存储不可用，请检查隐私模式或存储权限。"));
    request.onblocked = () => {
      blocked = true;
      reject(new Error("图片存储被另一个页面占用，请关闭旧页面后重试。"));
    };
    request.onsuccess = () => {
      if (blocked) request.result.close();
      else resolve(request.result);
    };
  });
}

export async function readAvatar(characterId: string): Promise<Blob | null> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const request = tx.objectStore(STORE).get(characterId);
    tx.oncomplete = () => {
      db.close();
      resolve(request.result instanceof Blob ? request.result : null);
    };
    tx.onabort = () => {
      db.close();
      reject(new Error("无法读取浏览器中的角色图片。"));
    };
  });
}

export async function saveAvatar(
  characterId: string,
  image: Blob | null,
): Promise<void> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    if (image) tx.objectStore(STORE).put(image, characterId);
    else tx.objectStore(STORE).delete(characterId);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onabort = () => {
      db.close();
      reject(
        new Error("图片未能保存，浏览器存储可能已满。请换一张较小的图片。"),
      );
    };
  });
}

export async function validateAvatar(file: File): Promise<void> {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type))
    throw new Error("请选择 PNG、JPEG 或 WebP 图片。");
  if (file.size > 10 * 1024 * 1024) throw new Error("图片不能超过 10 MiB。");
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error("无法读取这张图片，请换一张有效的图片。");
  }
  const pixels = bitmap.width * bitmap.height;
  bitmap.close();
  if (pixels > 32_000_000) throw new Error("图片不能超过 3200 万像素。");
}
