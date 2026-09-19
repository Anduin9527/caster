# CASTER 角色制作手账

中文 React + TypeScript + Vite 工作台。默认 `/` 使用真实后端；`?preview=1` 保留独立本地原型，演示任务与批准不会迁移到服务器。

## 运行

```bash
cd frontend
npm ci
npm run dev -- --port 4173 --strictPort
```

开发服务仅监听回环，`/api` 同源代理默认连接本机 `127.0.0.1:8189` SSH 隧道。隧道配置见 `../docs/OPERATIONS.md`；可通过 `CASTER_API_TARGET` 覆盖代理目标。不要将凭据写入客户端。构建使用 `npm run build`，本轮没有公开部署网站。

## 制作流程

角色模板 → 身份候选选一张 → 多套服装各三张候选、跨方案选一张 → 多姿态候选选一张 → 从这张姿态添加表情 → 审阅、透明输出与下载。

身份步骤采用基础服装；服装统一在第三步设计。当前唯一选择由服务器持久化，与历史批准分开。改选上游图片清除下游选择，保留旧资产和批准。模板可搜索、编辑、JSON 导入和保存；个人模板目前是共享后端的 `source=user`，尚无账号隔离。

默认工作台使用固定版本 Pose Studio 三维预设，按角色画布尺寸读取原生人偶渲染缓存，再作为 Qwen 的姿态参考。旧二维预设仅兼容历史记录。来源与版本见 `integrations/pose-studio-library.json`。

## 接口与数据边界

`src/production.ts` 封装真实制作接口，`src/library.ts` 访问模板库，`src/LiveWorkbench.tsx` 实现默认工作台。

- `/production/capabilities`、`/production/snapshot`：读取能力、真实任务、资产、批准、选择及批次。
- `/production/characters/{id}/outfits|selection|batches|manifest`：服装不可变版本、明确选用、批次与清单下载。
- `/production/characters/{id}/assets/{asset_id}/review`：表情审阅；审阅通过后可制作透明图片。
- `/production/pose-presets`：目录与图片只读；显式 POST 才保存姿态记录。
- `/assets/{id}/file`：原图及透明 PNG 下载。

批次请求先保存浏览器提交意图，不确定响应使用原幂等键核对。只取消排队任务；失败或待修正项明确重试并保留旧任务。待修正支持填写人脸像素区域。服务未运行时禁用生成，查询能力不会启动 ComfyUI。角色草稿、步骤与筛选偏好保存在浏览器，任务和批准以服务器为准。

## 本地预览与验证

`?preview=1` 使用 `src/model.ts`、`src/adapter.ts` 的演示状态；历史图片由 `predev`/`prebuild` 从 `samples/` 准备，不入 Git。缺失图片明确提示。演示 JSON 下载使用内存附件服务；Sites 或纯静态托管需要另行配置 API 和附件服务。

```bash
npm run typecheck
npm test
npm run build
npm run test:sites
```


## 加载与缓存

真实工作台启动只读取角色与制作记录；模板抽屉按 12 条分页，搜索防抖 250ms。分页使用浏览器 ETag 校验和 30 秒、40 页的内存缓存，成功写模板后清空页缓存。图卡请求 `/assets/{id}/thumbnail` 并懒加载，放大/下载读取原 PNG。Hub 模板按固定上游规则和真实图片地址显示配套参考图，浏览器懒加载；个人模板尚无图片上传入口。真实资产则使用后端缩略图。旧 `?preview=1` 保留原型的数据读取逻辑。


模板配图现在从 后端的 `data/template-previews/` 读取，前端不再直连外网图源。运维通过 `proxychains4 -q .venv/bin/python scripts/cache_template_previews.py --workers 8` 抓取/补齐，进度和失败清单为该目录下 `download-status.json`。下载不修改模板或生成记录；页面缓存缺失时明确提示图片暂不可用。


角色/作品译名与 Tag 双语显示来自服务端只读 `display` 字段，搜索支持中英文。原始英文 `name`、`tags`、`trigger` 不被翻译覆盖，编辑/导入剔除 display。标签缺译文时保留原文，不按近似名称自动猜译。
