# 快速开始

## 无 GPU 演示

以下命令在目标开发机器上执行。只预览界面可跳到前端步骤；前端独立安装，不需要 Python 环境。

### 1. 后端 API（仅模板和状态管理）

```bash
uv sync --locked --group dev
uv run --locked pytest -q  # 验证安装
AIGC_DATA_DIR="$PWD/data/local-dev" uv run --locked uvicorn aigc.api:app --host 127.0.0.1 --port 8189 --workers 1
```

成功启动后会显示：
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8189
```

验证：访问 <http://127.0.0.1:8189/health>，正常启动后返回 `{"status":"ok","worker_alive":true}`。

### 2. 前端工作台

另一个终端：
```bash
cd frontend
npm ci
npm run dev -- --port 4173 --strictPort
```

成功启动后会显示：
```
  ➜  Local:   http://127.0.0.1:4173/
```

### 3. 体验演示模式

- 打开 <http://127.0.0.1:4173/?preview=1> 查看前端演示（纯本地，不连后端）
- 打开 <http://127.0.0.1:8189/docs> 查看 API 文档

**注意**：
- 干净克隆缺少历史演示图，模板预览会显示占位符
- API 没有模拟生成模式；未接通 ComfyUI 时不要提交真实推理任务

---

## 完整生成环境（需要 GPU）

参见 [运行手册](OPERATIONS.md) 的完整部署指南。

简要步骤：
1. 安装 ComfyUI 和[必需依赖](DEPENDENCIES.md)
2. 下载模型和自定义节点
3. 配置 `config.env`（ComfyUI 地址、数据目录）
4. 运行服务脚本或手动启动
5. 缓存模板预览和 Pose Studio 渲染图

未完成上述步骤时，工作台可以浏览模板和历史记录，但提交生成任务会失败。
