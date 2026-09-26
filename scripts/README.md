# 项目工具

## 启动与服务

- `run.sh`：读取本地 `config.env`，启动后端。
- `service.py`：Linux 后端服务启动、状态与停止。
- `aigc.py`：命令行 API 客户端。

## 模板与资源

- `import_anima_hub.py`：重建锁定的 Hub 角色/历史服装快照，不用于当前产品服装库。
- `promote_outfit_catalog.py`：将已审批的 50 套 catalog 原子替换为正式服装模板。
- `map_template_names.py`：构建中文名称与标签映射。
- `cache_template_previews.py`：缓存模板配图。
- `cache_pose_studio.py`：缓存姿态资源。
- `render_pose_studio.py`、`pose-studio-render.html`：渲染姿态人偶。

## 工作流与导出

- `export_ui.py`：导出 ComfyUI 可视工作流。
- `probe_workflow.py`：提交指定工作流并收集结果。
- `verify_pixels.py`：检查局部编辑的掩码外像素。

## RAG 维护

- `prepare_rag_wiki.py`、`rag_build_bodies.py`、`rag_build_index.py`：准备 Wiki 正文并构建索引。
- `rag_publish_alias.py`、`rag_verify_index.py`：验证并发布版本化 Qdrant alias。
- `rag_search_smoke.py`：对已部署索引做只读烟雾检查。
- `rag_eval_live_backend.py`：用冻结查询集评估实际检索路径。
- `rag_snapshot_templates.py`、`rag_fetch_models.py`、`verify_rag_wiki.py`：准备模板快照、模型和语料验证。
- `rag_encoder.py`：复用包内编码器，默认查找当前源码目录；独立工作区可设置 `AIGC_PACKAGE_ROOT`。

索引准备、发布和评估约定见 [RAG 维护](../docs/RAG.md)。旧探针与逐轮验收脚本归档在忽略的
`data/local-history/`，不作为安装或生产部署依赖。

## 开发检查

- `check_repository.py`：检查源码候选文件中是否混入运行数据，检查 Markdown 本地链接。
- 根目录 `make check`：运行完整的后端与前端检查；见[贡献指南](../CONTRIBUTING.md)。

角色制作流程见 [Skill](../.agents/skills/caster-character-production/SKILL.md)。私人部署脚本仅在本地维护。

通用工具通过 `aigc/config.py` 读取根目录 `config.env`；显式环境变量和工具命令行参数可覆盖默认值。`start_api.py` 是后端启动入口，`_config.py` 是脚本共享读取模块。
