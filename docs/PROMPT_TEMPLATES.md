# 角色与服装模板

CASTER 把角色与服装作为两类独立模板。角色库来自固定版本的
[Comfyui-Anima-Tools-HUB](https://github.com/j955229/Comfyui-Anima-Tools-HUB)；当前产品服装库是
`integrations/curated-outfits-v1.json` 中的 50 套模板。服装模板不包含画师风格、固定质量词或
通用负面词，这些由 Anima 运行时设置管理。

上游快照 `a0c351e81a24ebdbc7f47c524139a8dfe1226705` 包含 7,999 个角色和 430 套历史服装；
后者只作为来源参考，不再是正式产品目录。来源、版本与 SHA256 见
`integrations/anima-hub.json`。上游完整数据和图库不进 Git，需要时才下载到已忽略的 `data/`。

## 导入与更新

`scripts/import_anima_hub.py` 用于重建上游快照，会同时包含历史的 430 套服装。不要将它直接
导入当前产品数据库，否则会重新引入已淘汰目录。它的用途是重建角色源数据、溯源或离线研究：

在本地项目根目录：

```bash
uv run --locked python scripts/import_anima_hub.py
```

默认只生成 `data/anima-hub.templates.json` 和来源清单。传入 `--data-dir` 才会写本地数据库。
已有本地文件可用 `--source-dir /path/to/hub`，目录须含原版 `js/` 文件并通过固定哈希校验。

正式 50 套服装由维护脚本从已审批 catalog 原子替换：

```bash
uv run --locked python scripts/promote_outfit_catalog.py --help
```

该操作会修改模板库，必须使用脚本要求的 catalog/settings 审批哈希。不要在普通启动或部署时自动执行。

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
