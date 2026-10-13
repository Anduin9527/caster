# 运行手册

## 后端

安装 Python 3.12 和 uv，在项目根目录执行：

```bash
uv sync --locked --group dev
cp config.env.example config.env
# 编辑 config.env，设置 AIGC_DATA_DIR 和 AIGC_COMFY_URL
bash scripts/run.sh
```

`config.env` 仅保存在本地。后端默认监听 `127.0.0.1:8189`，API 文档位于 `/docs`，
正式接口为 `/api/v1`，健康检查位于 `/api/v1/health`。旧 `/health` 和无前缀接口保留兼容。

## 前端

```bash
cd frontend
npm ci
npm run dev -- --port 4173 --strictPort
```

前端默认代理到本地后端。使用远程服务时，在本地建立 SSH 隧道，或按前端说明配置代理目标。

前端可单独复制 `frontend/` 后构建，静态产物位于 `dist/client/`。同源部署的反向代理必须将
`/api/v1/` 原样转发到后端，关闭 SSE 响应缓冲；示例见 [nginx 配置](../frontend/deploy/nginx.conf)。
直接跨域部署时，在前端构建环境设置 `VITE_API_BASE_URL=http://127.0.0.1:8189/api/v1`，
后端设置 `AIGC_CORS_ORIGINS=http://127.0.0.1:4173`。网址填写浏览器实际可访问的地址；
远程回环服务通过 SSH 隧道访问。两个配置都不包含模型密钥。

先升级后端以提供 `/api/v1`，再部署新前端。旧前端仍可经原代理访问兼容路径；后端回滚时，
应同时回滚前端静态包及其代理配置。源码发布不覆盖 `AIGC_DATA_DIR`。

## ComfyUI

节点、模型与固定版本见 [依赖说明](DEPENDENCIES.md)。在 ComfyUI 中安装项目 `custom_nodes/AIGC_LocalEdit`，使用 `workflows/` 的工作流和参数绑定。模型清单记录上游文件、版本及哈希，模型安装位置由本地 ComfyUI 配置确定。

机器专用安装、下载和服务管理脚本由部署环境维护。仓库不包含私人 SSH 地址或代理配置。

## 数据与服务管理

`AIGC_DATA_DIR` 保存数据库、模板、缓存和资产。升级时备份该目录，再同步源码并安装锁定依赖。ComfyUI 使用独立 GPU 环境，生成任务串行执行。

后端服务管理可用 `scripts/service.py start|status|stop`；该脚本用于 Linux，按 `config.env` 中的 `AIGC_API_URL` 检查服务。前端接口详情见 [前端说明](../frontend/README.md)。
