# Anima 角色与服装模板

CASTER 将 [Comfyui-Anima-Tools-HUB](https://github.com/j955229/Comfyui-Anima-Tools-HUB) 的人物、服装数据适配为独立模板库，供现有 AnimaYume 文生图使用。当前交付是后端 API、导入工具与自定义 JSON 上传，不包含上游 Hub 的 ComfyUI 卡片界面、预览图库、随机选择器、LoRA 管理器或 LLM 节点。

固定上游版本 `a0c351e81a24ebdbc7f47c524139a8dfe1226705`：`js/character_official_data.json` 中 7,999 个角色，`js/clothing_data.js` 中 430 套服装。来源、版本、文件 SHA256 见 `integrations/anima-hub.json`。上游 `pyproject.toml` 声明 MIT，仓库树未见独立 LICENSE 文件；本集成不将上游代码、图库或完整数据复制进 Git。需要时显式下载到忽略的 `data/`。导入脚本核对固定 SHA256，解析 JSON 字面量，不运行下载的 JS；不下载预览图。

## 导入上游库

在本地项目根目录：

```bash
uv run --locked python scripts/import_anima_hub.py --data-dir data
```

默认生成 `data/anima-hub.templates.json` 和来源清单，同时导入本地 `data/state.sqlite3`。如果设置了 `AIGC_DATA_DIR`，请将 `--data-dir` 显式指向相同目录。已有本地文件可用 `--source-dir /path/to/hub`，目录须含原版 `js/` 文件，并通过固定版本哈希校验。

向已部署 API 导入时只提交 JSON，不复制或覆盖运行数据库：

```bash
curl -F 'file=@data/anima-hub.templates.json' http://127.0.0.1:8189/prompt-templates/import
```

此命令要求目标 API 已部署新功能。当前本地开发不自动部署或重启远端服务。

导入为事务操作：相同 ID 与相同内容重复提交只跳过；相同 ID 内容不同返回 409，整批回滚，不覆盖用户编辑。不同上游 revision 对应不同模板 ID。当前 bundle v1 每次最多 10,000 项、16 MiB。

## 搜索、预览和创建角色

API 文档入口 `/docs` 的 **Prompt templates** 分组可以直接操作。

```bash
curl -G http://127.0.0.1:8189/prompt-templates --data-urlencode 'kind=character' --data-urlencode 'q=hatsune miku'
curl -G http://127.0.0.1:8189/prompt-templates --data-urlencode 'kind=outfit' --data-urlencode 'q=外套'
```

列表响应 `{total, items}`，支持 `category` 精确分类、`offset` 和 `limit`（默认 50、最大 200）。名称、原始标签、作品分类均可搜索。生成提示词使用上游英文标签；中文译名只用于查找与展示。

将返回的模板 ID 放入请求：

```json
{
  "character_template_id": "CHARACTER_TEMPLATE_ID",
  "outfit_template_ids": ["OUTFIT_TEMPLATE_ID"],
  "character_id": "my-test-hero",
  "name": "测试主角",
  "include_character_tags": true
}
```

- `POST /prompt-templates/preview`：返回角色数据和每套服装的正负提示词，不创建角色或任务。
- `POST /prompt-templates/instantiate`：保存新角色、服装和完整模板快照，返回相同预览。已有角色 ID 返回 409。
- 接着按原流程创建 `/scene-specs`：`character_id` 用 `my-test-hero`，`outfit_id` 用所选服装模板 ID，`asset_type` 用 `sprite`；提交 `/jobs` 才开始推理。

人物库的外观标签可能包含原作服装、重复项或多个发色/眼色。可将 `include_character_tags` 设为 false，仅使用角色触发词；或先将条目复制成自己的 ID，编辑为目标形象。预览不保证模型服装跟随或身份一致，需要实际看图验收。

模板编辑不会修改已创建角色的标签、服装或模板快照。需要采用新模板时创建新角色 ID。模板导入、预览、角色创建均不产生图片批准；姿态与表情继续遵守现有批准约束。

## 自定义小说主角模板

示例见 `examples/prompt-templates.json`。通过 JSON 文件上传：

```bash
curl -F 'file=@examples/prompt-templates.json' http://127.0.0.1:8189/prompt-templates/import
```

`kind` 为 `character` 或 `outfit`，`trigger`、`tags`、`description` 至少有一个非空；`description` 保留自然语言，不做标签去重。可用 `categories` 按小说、角色、服装用途分组。仅解析数据，不解释其中的命令或指令。

维护接口：

| 接口 | 用途 |
| --- | --- |
| `POST /prompt-templates` | 新建单个模板，自定义 ID |
| `GET /prompt-templates/{id}` | 查看完整模板及来源 |
| `PUT /prompt-templates/{id}` | 提交完整模板替换内容，ID 和类型不变 |
| `GET /prompt-templates/export` | 导出 bundle v1，供备份和移交 |

当前为单用户、回环监听的开发服务，未实现多用户隔离或浏览器文件管理界面。后续产品 UI 可直接调用上述接口。
