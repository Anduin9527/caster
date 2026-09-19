export const expressionPresets = [
  { name: "开心", prompt: "a gentle happy smile" },
  { name: "惊讶", prompt: "a surprised expression" },
  { name: "生气", prompt: "an angry expression" },
  { name: "大笑", prompt: "a joyful laughing expression" },
  { name: "难过", prompt: "a sad expression" },
  { name: "哭泣", prompt: "a crying expression with tears" },
  { name: "害羞", prompt: "a shy blushing expression" },
  { name: "疑惑", prompt: "a puzzled expression" },
  { name: "担心", prompt: "a worried expression" },
  { name: "害怕", prompt: "a frightened expression" },
  { name: "得意", prompt: "a confident smug smile" },
  { name: "困倦", prompt: "a sleepy expression" },
  { name: "认真", prompt: "a serious focused expression" },
  { name: "眨眼", prompt: "a playful wink" },
  { name: "无奈", prompt: "an exasperated expression" },
];

export function expressionLabel(
  prompt?: string,
  custom = expressionPresets,
): string {
  if (!prompt || prompt === "neutral expression") return "自然表情";
  return (
    custom.find((m) => m.prompt === prompt)?.name ||
    expressionPresets.find((m) => m.prompt === prompt)?.name ||
    "自定义表情"
  );
}
export function assetTypeLabel(type?: string): string {
  return (
    {
      sprite: "角色图片",
      identity: "角色图片",
      outfit: "换装图片",
      pose: "姿态图片",
      expression: "表情图片",
      matte: "透明图片",
      background: "背景图片",
    }[type || ""] || "图片"
  );
}
export function jobErrorLabel(error?: string): string {
  if (/face|mask|crop/i.test(error || ""))
    return "未能准确定位脸部，请重新指定人脸区域。";
  if (/memory|cuda/i.test(error || "")) return "图片处理资源不足，请稍后重试。";
  if (/history|uncertain/i.test(error || ""))
    return "正在核对制作结果，请勿重复提交。";
  if (/connect|timeout|network/i.test(error || ""))
    return "与图片服务的连接中断，请稍后重试。";
  return "本次制作未完成，请重试或调整所选图片。";
}
