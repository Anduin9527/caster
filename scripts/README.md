# 项目工具

## 启动与服务

- `run.sh`：读取本地 `config.env`，启动后端。
- `service.py`：Linux 后端服务启动、状态与停止。
- `aigc.py`：命令行 API 客户端。

## 模板与资源

- `import_anima_hub.py`：导入角色与服装模板。
- `map_template_names.py`：构建中文名称与标签映射。
- `cache_template_previews.py`：缓存模板配图。
- `cache_pose_studio.py`：缓存姿态资源。
- `render_pose_studio.py`、`pose-studio-render.html`：渲染姿态人偶。

## 工作流与导出

- `export_ui.py`：导出 ComfyUI 可视工作流。
- `probe_workflow.py`：提交指定工作流并收集结果。
- `verify_pixels.py`：检查局部编辑的掩码外像素。

角色制作流程见 [Skill](../.agents/skills/caster-character-production/SKILL.md)。私人部署脚本仅在本地维护。

通用工具通过 `aigc/config.py` 读取根目录 `config.env`；显式环境变量和工具命令行参数可覆盖默认值。`start_api.py` 是后端启动入口，`_config.py` 是脚本共享读取模块。
