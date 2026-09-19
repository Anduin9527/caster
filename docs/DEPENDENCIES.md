# 依赖说明

## 必需依赖（完整生成环境）

### 1. ComfyUI 主体
- 仓库：https://github.com/comfyanonymous/ComfyUI
- 用途：模型加载、节点执行与生成队列

### 2. 自定义节点
| 节点包 | 来源 | 用途 | 是否必需 |
|--------|------|------|----------|
| AIGC_LocalEdit | `custom_nodes/AIGC_LocalEdit/` | 脸部裁剪、掩码回贴 | **必需** |
| CASTER_AnimaControl | `custom_nodes/CASTER_AnimaControl/` | 姿态控制实验 | 可选 |
| ComfyUI_VNCCS | 上游 | Qwen 多图编码 | **必需** |
| ComfyUI_VNCCS_Utils | 上游 | Pose Studio 渲染 | **必需** |

安装方式：
```bash
cd ComfyUI/custom_nodes
# 安装上游节点
git clone https://github.com/AHEKOT/ComfyUI_VNCCS
git clone https://github.com/AHEKOT/ComfyUI_VNCCS_Utils

# 链接本项目节点
ln -s /path/to/caster/custom_nodes/AIGC_LocalEdit .
ln -s /path/to/caster/custom_nodes/CASTER_AnimaControl .  # 可选
```

### 3. 模型
参考 `models-manifest.json` 和 `additional-models-manifest.json`。

主要模型：
- **AnimaYume v15**：角色原图和换装
- **Qwen Image Edit 2511**：动作和表情编辑
- **BiRefNet**：透明抠图
- **Pose Studio LoRA**：姿态控制
- **SAM**：脸部掩码生成

模型下载脚本：
```bash
# 按 models-manifest.json 和 additional-models-manifest.json 下载固定版本模型到 ComfyUI
```

### 4. Python 和 Node.js
- Python 3.12（推荐使用 uv 管理）
- Node.js 22.x / npm
- uv（Python 包管理器）

---

## 可选依赖

### 开发工具
- pytest：单元测试
- ruff：代码检查
- Vitest：前端测试

### 实验功能
- `scripts/render_pose_studio.py`：本地渲染 Pose Studio 人偶（需要浏览器）

---

## 硬件要求

### 已验证配置
- GPU：RTX 4090 24GB VRAM
- 系统：Linux（Ubuntu/Debian）

配置说明：
- 启用低显存模式和 CPU VAE
- 串行推理（一次一个任务）
- 支持的画布尺寸：1024×1536 及其他预设

### 较小配置（社区反馈）
更小的显存（如 RTX 3060 12GB）可能可用，但需要：
- 调整批量大小
- 启用模型量化
- 减少并发任务

---

## 安装顺序

1. 安装 Python 3.12 和 uv
2. 克隆本项目：`git clone <repo>`
3. 安装 Python 依赖：`uv sync --locked --group dev`
4. 安装 ComfyUI（独立目录）
5. 安装 ComfyUI 自定义节点（上游 + 本项目）
6. 下载模型到 ComfyUI 模型目录
7. 配置 `config.env`（见 `config.env.example`）
8. 运行测试：`uv run pytest -q`
9. 缓存模板预览：`uv run python scripts/cache_template_previews.py`
10. 缓存 Pose Studio：`uv run python scripts/cache_pose_studio.py`

详细命令见 [运行手册](OPERATIONS.md)。
