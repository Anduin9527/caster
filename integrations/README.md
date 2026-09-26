# Integrations 目录说明

本目录保存**上游资源清单**：模板来源、固定版本、预设定义和翻译表。

## 文件说明

### 模板与配图来源
- `curated-outfits-v1.json` — 当前 50 套正式服装的配方源；图片可留空
- `anima-hub.json` — Anima 角色库和历史服装快照的上游版本
- `anima-outfit-previews.json` — 历史上游服装的预览图映射，不是当前 50 套的图库
- `anima-pose-control.json` — 姿态控制实验的配置

### Pose Studio
- `pose-studio-library.json` — Pose Studio 预设姿态库清单
- `vnccs-poses.json` — VNCCS 示例姿态的元数据

### 翻译与本地化
- `ffdkj-translations.json` — Danbooru 中英翻译表来源

### 画布预设
- `canvas-presets.json` — 支持的画布尺寸和比例定义

## 使用方式

这些文件被以下脚本和模块读取：
- `scripts/import_anima_hub.py` — 重建锁定的 Hub 快照（包含历史服装）
- `scripts/promote_outfit_catalog.py` — 将已审批的 50 套服装原子替换为正式模板
- `scripts/cache_template_previews.py` — 缓存模板配图
- `scripts/cache_pose_studio.py` — 缓存 Pose Studio 渲染图
- `aigc/templates.py` — 加载模板定义
- `aigc/canvas.py` — 加载画布预设

## 版本锁定

**重要**：这些 JSON 文件锁定了上游资源的特定版本（commit hash、文件校验和）。

修改前务必确认：
1. 上游资源是否有更新
2. 更新是否兼容现有工作流
3. 是否需要同步更新 `models-manifest.json` 或 `nodes-manifest.json`

## 与根目录 manifest 的关系

根目录的三个 manifest 文件记录模型来源、版本、哈希与节点补丁，生成任务会保存这些信息用于追溯：
- `models-manifest.json` — 模型下载清单
- `nodes-manifest.json` — 自定义节点安装清单
- `additional-models-manifest.json` — 额外模型（实验功能）

`integrations/` 中的文件是**配置清单**，定义模板、翻译、预设等数据来源。

两者职责不同，但都需要同步维护以保证版本一致性。

## 节点补丁

`patches/` 保存节点适配补丁，根目录 `nodes-manifest.json` 的 `patch_file` 指向对应文件。补丁与上游固定版本一起维护。
