# 运行手册

## 后端

安装 Python 3.12 和 uv，在项目根目录执行：

```bash
uv sync --locked --group dev
cp config.env.example config.env
# 编辑 config.env，设置 AIGC_DATA_DIR 和 AIGC_COMFY_URL
bash scripts/run.sh
```

`config.env` 仅保存在本地。后端默认监听 `127.0.0.1:8189`，API 文档位于 `/docs`，健康检查位于 `/health`。

## 前端

```bash
cd frontend
npm ci
npm run dev -- --port 4173 --strictPort
```

前端默认代理到本地后端。使用远程服务时，在本地建立 SSH 隧道，或按前端说明配置代理目标。

## ComfyUI

节点、模型与固定版本见 [依赖说明](DEPENDENCIES.md)。在 ComfyUI 中安装项目 `custom_nodes/AIGC_LocalEdit`，使用 `workflows/` 的工作流和参数绑定。模型清单记录上游文件、版本及哈希，模型安装位置由本地 ComfyUI 配置确定。

机器专用安装、下载和服务管理脚本由部署环境维护。仓库不包含私人 SSH 地址或代理配置。

## 数据与服务管理

`AIGC_DATA_DIR` 保存数据库、模板、缓存和资产。升级时备份该目录，再同步源码并安装锁定依赖。ComfyUI 使用独立 GPU 环境，生成任务串行执行。

后端服务管理可用 `scripts/service.py start|status|stop`；该脚本用于 Linux，默认检查本地 8189 端口。前端接口详情见 [前端说明](../frontend/README.md)。
