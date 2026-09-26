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
| ComfyUI-Impact-Pack / Subpack | 上游 | SAM 与人脸检测器 | **必需** |
| ComfyUI-RMBG | 上游 | BiRefNet 抠图 | **必需** |

安装方式：
```bash
cd ComfyUI/custom_nodes
# 安装上游节点
git clone https://github.com/AHEKOT/ComfyUI_VNCCS
git clone https://github.com/AHEKOT/ComfyUI_VNCCS_Utils
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack
git clone https://github.com/ltdrdata/ComfyUI-Impact-Subpack
git clone https://github.com/1038lab/ComfyUI-RMBG
# 各节点切换至 nodes-manifest.json 记录的 commit，再安装其 requirements.txt

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

按清单中的 URL 下载并校验 SHA256，再放入 ComfyUI 对应的模型目录。节点适配补丁由 `nodes-manifest.json` 的 `patch_file` 指定。

### 4. Python 和 Node.js
- Python 3.12（推荐使用 uv 管理）
- Node.js 22.x / npm
- uv（Python 包管理器）

---

## 可选依赖

### 开发工具
- pytest：单元测试
- Ruff：Python 静态检查与统一格式，版本由 `uv.lock` 固定
- Node.js test runner / tsx：前端测试

### 实验功能
- `scripts/render_pose_studio.py`：本地渲染 Pose Studio 人偶（需要浏览器）

### Agent 助手（`aigc/agent/`）
- `llama-index-core>=0.14.25`：唯一的 Agent 编排框架（FunctionAgent 工具循环）
- `llama-index-llms-openai-like>=0.8.0`：OpenAI 兼容对话模型客户端
- 本地基础检索提供模板库的精确匹配与 BM25；配置 `AIGC_RAG_DIR` 后可接入 Qwen3 Embedding
  和独立部署的 Qdrant 服务
- `qdrant-client` 已锁定在开发依赖中；Qwen 推理环境与权重由服务器 RAG 工作区管理，不与
  ComfyUI 环境混装。当前运行边界见 [系统架构](ARCHITECTURE.md)
- 索引构建、配置与独立评估见 [RAG 维护](RAG.md)

这两个包是纯 Python 依赖树，已由 `uv.lock` 固定；安装后不影响 ComfyUI 的 GPU 调度。

---

## 硬件要求

### 已验证配置
- GPU：RTX 4090 24GB VRAM
- 系统：Linux（Ubuntu/Debian）

配置说明：
- 启用低显存模式和 CPU VAE
- 串行推理（一次一个任务）
- 支持的画布尺寸：1024×1536 及其他预设

其他硬件配置尚未验证。

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
