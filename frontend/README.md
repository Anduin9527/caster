# CASTER 工作台

中文 React 19 + TypeScript + Vite + TanStack Query 工作台。默认 `/` 使用真实后端；`?preview=1` 保留独立本地原型，演示任务与批准不会迁移到服务器。

## 运行

```bash
cd frontend
npm ci
npm run dev -- --port 4173 --strictPort
```

在目标开发机器上运行 Node.js 22.12+。开发服务默认监听回环，`/api/v1` 同源代理连接 `127.0.0.1:8189`，
转发时保留完整路径。远程访问见[运行手册](../docs/OPERATIONS.md)。

可以仅复制整个 `frontend/` 目录运行上述命令，无需 Python、后端源码、`integrations/`、`docs/` 或 `.venv`。
`AIGC_API_URL` 与 `AIGC_UI_URL` 的读取顺序为进程环境、前端 `.env`、根目录 `config.env`、默认值；
`AIGC_CONFIG_FILE` 可选择兼容配置文件。前端 `.env` 示例见 [配置示例](.env.example)。模型凭据由后端管理。

## 独立部署

```bash
npm ci
npm run build
```

将 `dist/client/` 作为静态网站托管。同源部署配置 `/api/v1/` 的反向代理，保留路径并关闭 SSE 缓冲；
参考 [nginx 示例](deploy/nginx.conf)。`npm run preview -- --host 127.0.0.1 --port 4173` 可在开发机器检查构建结果，
预览代理同样使用 `AIGC_API_URL`。Sites 原有打包文件继续生成，静态 Sites 部署需配置可访问的独立 API。

跨域部署时，在构建前设置 `VITE_API_BASE_URL`，例如 `http://127.0.0.1:8189/api/v1`；
后端 `AIGC_CORS_ORIGINS` 配置前端的精确 origin，例如 `http://127.0.0.1:4173`。
JSON、SSE、图片和下载均使用该地址。`VITE_*` 会进入公开浏览器代码，不存放密钥。
部署地址变化需要重新构建前端。此配置不增加身份认证；服务保持回环监听，通过 SSH 隧道访问。

## 制作流程

角色模板 → 身份候选选一张 → 多套服装各三张候选、跨方案选一张 → 多姿态候选选一张 → 从这张姿态添加表情 → 审阅、透明输出与下载。

身份步骤采用基础服装；服装统一在第三步设计。当前唯一选择由服务器持久化，与历史批准分开。改选上游图片清除下游选择，保留旧资产和批准。模板可搜索、编辑、JSON 导入和保存；个人模板目前是共享后端的 `source=user`，尚无账号隔离。

默认工作台使用固定版本 Pose Studio 三维预设，按角色画布尺寸读取原生人偶渲染缓存，再作为 Qwen 的姿态参考。旧二维预设仅兼容历史记录。来源与版本见 `integrations/pose-studio-library.json`。

## 接口与数据边界

`src/production.ts` 封装真实制作接口，`src/library.ts` 访问模板库，`src/LiveWorkbench.tsx` 实现默认工作台。

`src/AgentPanel.tsx` 管理对话与事件流；`src/agent/` 分别显示连接设置、检索证据、工具轨迹和审批卡。
`src/agent.ts` 封装 Agent 接口与公开类型。历史演示通过动态导入仅在 `?preview=1` 下加载。

`src/api/http.ts` 统一请求和媒体 URL。`src/workbench/` 管理查询缓存、轮询与切换取消，
`LiveWorkbench` 保留交互和草稿状态。工作台的服务端类型来自 `src/api/schema.d.ts`，
通过 `openapi.json` 生成；API 路径以下均相对于 `/api/v1`。

- `/production/capabilities`、`/production/snapshot`：读取能力、真实任务、资产、批准、选择及批次。
- `/production/characters/{id}/outfits|selection|batches|manifest`：服装不可变版本、明确选用、批次与清单下载。
- `/production/characters/{id}/assets/{asset_id}/review`：表情审阅；审阅通过后可制作透明图片。
- `/production/pose-presets`：目录与图片只读；显式 POST 才保存姿态记录。
- `/assets/{id}/file`：原图及透明 PNG 下载。

批次请求先保存浏览器提交意图，不确定响应使用原幂等键核对。只取消排队任务；失败或待修正项明确重试并保留旧任务。待修正支持填写人脸像素区域。服务未运行时禁用生成，查询能力不会启动 ComfyUI。角色草稿、步骤与筛选偏好保存在浏览器，任务和批准以服务器为准。

新角色可上传可选头像参考（PNG/JPEG/WebP，最大 10 MiB、3200 万像素）。Blob 以角色 ID 存入 IndexedDB，仅在角色卡片展示，不上传后端、不参与生成或候选选择。表单编辑保留标签原文与光标，提交时才按逗号、中文逗号或换行整理。

模型连接由后端持续保存；勾选浏览器记忆时，连接与密钥另存当前 origin 的 localStorage。后端未配置时浏览器副本自动填入表单，仍需用户保存后才应用，不自动覆盖其他后端。切换服务地址会清空密钥输入，保留旧密钥仅限同一地址；界面支持清除浏览器副本。不同端口和浏览器不共享该存储。

## 本地预览与验证

`?preview=1` 使用 `src/model.ts`、`src/adapter.ts` 的演示状态；历史图片由 `predev`/`prebuild` 从 `samples/` 准备，不入 Git。缺失图片明确提示。演示 JSON 下载使用内存附件服务；Sites 或纯静态托管需要另行配置 API 和附件服务。

```bash
npm run check
```

接口修改在完整源码中执行 `make contracts`，生成最新 `openapi.json`、TypeScript 类型和只读目录副本。
仅有前端时，使用 `npm run generate:api` 从已提交的契约生成类型；`npm run check:api` 检查漂移。
生成器有独立的 `tools/openapi/` workspace 与兼容编译器，应用 TypeScript 版本保持不变。

## 加载与缓存

真实工作台按角色隔离快照缓存，同键请求共享，切换角色和卸载时取消旧读请求。快照与能力每 5 秒刷新；
姿态目录缓存 5 分钟，隐藏页面暂停轮询；写操作成功后使缓存失效。写操作不自动重试，保留提交意图与原幂等键。
模板抽屉按 12 条分页，搜索防抖 250ms。分页使用浏览器 ETag 校验和 30 秒、40 页的内存缓存，成功写模板后清空页缓存。
图卡请求 `/assets/{id}/thumbnail` 并懒加载，放大/下载读取原 PNG。个人模板尚无图片上传入口。
旧 `?preview=1` 保留原型的数据读取逻辑。


模板配图现在从 后端的 `data/template-previews/` 读取，前端不再直连外网图源。运维通过 `proxychains4 -q .venv/bin/python scripts/cache_template_previews.py --workers 8` 抓取/补齐，进度和失败清单为该目录下 `download-status.json`。下载不修改模板或生成记录；页面缓存缺失时明确提示图片暂不可用。


角色/作品译名与 Tag 双语显示来自服务端只读 `display` 字段，搜索支持中英文。原始英文 `name`、`tags`、`trigger` 不被翻译覆盖，编辑/导入剔除 display。标签缺译文时保留原文，不按近似名称自动猜译。
