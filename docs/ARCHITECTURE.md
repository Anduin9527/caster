# CASTER 架构

CASTER 是一个单用户、回环部署的角色资产制作工作台。React 前端负责分步制作与人工审批，
FastAPI + SQLite 保存模板、角色、资产、计划和任务，ComfyUI 只负责执行已经批准的生成工作流。

## 前后端分离

- 前端：React 19 + TypeScript + Vite。TanStack Query 管理角色目录、按角色隔离的制作快照、
  能力状态、姿态目录和提示词设置；草稿、选图偏好和待核对的提交意图继续使用各自的浏览器持久化。
- 后端：FastAPI + Pydantic 2。原生提供 `/api/v1`，开发代理与部署代理均保留完整路径，
  无需删除 `/api` 前缀。旧无前缀路径保留兼容，公开 OpenAPI 只描述版本化接口。
- 契约：`aigc/http_contracts.py` 描述工作台读模型，输入继续使用领域模型。
  `scripts/export_openapi.py` 在不启动服务、不读运行数据的情况下导出 `frontend/openapi.json`；
  openapi-typescript 生成 `frontend/src/api/schema.d.ts`，工作台直接引用这些类型。
  Agent 的动态事件展示类型仍由助手模块维护，未宣称所有历史接口都具有完整响应模型。
- 传输：`frontend/src/api/http.ts` 统一根地址、超时、取消与 HTTP 错误。
  JSON、SSE、缩略图、原图、模板预览、姿态图片和清单下载均通过同一地址配置。
  `VITE_API_BASE_URL` 可设置为同源路径或绝对 URL；跨域时后端只允许 `AIGC_CORS_ORIGINS` 列出的精确 origin。
- 构建：`frontend/` 自带品牌图片和生成的只读目录副本，不直接导入仓库外层的后端、文档或资源文件。
  只读目录源仍为 `integrations/`，`make contracts` 同步副本，CI 检查内容一致。
  OpenAPI 生成工具使用独立 npm workspace，锁定其需要的 TypeScript 5，应用保持 TypeScript 7。

前端构建产物为 `frontend/dist/client/`，可以作为静态文件独立托管。后端不承担 SPA 文件服务，
两端通过 HTTP/SSE 协作；部署与回滚无需复制数据库或生成资产。CORS 仅用于跨域访问配置，
系统仍按单用户回环部署设计，不增加账号隔离或公开互联网访问授权。

实现依据：[TanStack Query 的请求取消](https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation)、
[查询默认行为](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults)、
[OpenAPI TypeScript](https://openapi-ts.dev/cli)、[FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)。

## 模块与资源生命周期

`aigc.api.create_app()` 组装应用；保留 `aigc.api:app` 部署入口。应用导入或生成 OpenAPI 时不创建数据库、
HTTP 客户端或 worker。每个应用实例使用自己的配置、Store、AgentEngine 和 ComfyUI 客户端，生命周期
负责恢复 Agent 中断轮次、同步模板，并在关闭时结束 Agent 任务、释放客户端。生成 Worker 使用独立进程，
API 不获取执行锁，也不执行已入队的生成任务。事务 outbox、RabbitMQ 与恢复协议见[任务执行架构](TASK_EXECUTION.md)。

| 模块 | 职责 |
| --- | --- |
| `aigc/routes/` | 场景、资产、任务 HTTP 接口与输入校验 |
| `aigc/agent/` | 会话事件、检索证据、工具、计划、人工审批 |
| `aigc/agent/engine.py` | 应用内运行状态、取消、超时、失败重试与关闭 |
| `aigc/agent/backend.py` | LlamaIndex 模型与工具循环适配 |
| `aigc/agent/events.py` | SQLite 有序事件追加、游标分页与重连恢复 |
| `aigc/workbench.py`、`aigc/production.py` | 当前选图、不可变版本、制作批次与快照 |
| `aigc/worker.py` | 串行执行、授权复核、ComfyUI history 恢复、输出验证 |
| `aigc/worker_main.py` | 独立执行进程、GPU 锁、心跳与退出回收 |
| `aigc/delivery.py` | 事务 outbox、持久化接收、提交 CAS、安全重试与状态事件 |
| `aigc/broker.py` | RabbitMQ 发布确认、消息接收与手动 ACK、死信拓扑 |
| `aigc/job_snapshot.py` | 工作台与兼容入队接口的冻结输入快照 |
| `aigc/store.py` | SQLite 事务与持久化；事务结束时关闭连接 |
| `aigc/rag*.py` | 查询、编码器、索引指纹与 Wiki 正文目录 |
| `frontend/src/agent/` | 会话请求与事件流生命周期、连接设置、证据、工具轨迹与审批卡 |
| `frontend/src/api/` | 统一 HTTP 传输、地址处理与生成的契约类型 |
| `frontend/src/workbench/` | 查询键、缓存、轮询、请求取消与服务端数据钩子 |
| `frontend/src/workbenchPreferences.ts` | 随角色一次切换的制作偏好与持久化 |

路由通过工厂取得应用资源；测试注入临时 Store 和离线适配器，不替换进程级数据库全局变量。
历史演示按需加载，前端配置读取由 Node 完成，构建不依赖后端虚拟环境。

## 制作链路

```text
角色模板 → 身份候选 → 服装候选 → 姿态候选 → 表情编辑 → 透明 PNG
```

- 身份和服装使用 Anima；姿态与表情使用 Qwen Image Edit；透明抠图使用 BiRefNet。
- 每一步都保存来源图和不可变版本。选择新上游图片会使下游选择失效，但不删除历史资产。
- 后端串行提交 GPU 任务，并用幂等键、ComfyUI prompt ID 和 history 恢复不确定提交。
- 表情从已批准的姿态图分支，只修改有效脸部掩码；掩码外像素必须保持不变。

## Agent

生产 Agent 统一使用 LlamaIndex `FunctionAgent`。LlamaIndex 管理系统提示、工具 schema、工具循环、
scratchpad 和 `role=tool` 回填；业务代码只实现受限工具函数、领域校验和结构化 UI 事件。

当前工具覆盖：

- 读取工作台、角色和模板候选；
- 查询 Wiki 标签知识；
- 准备角色/服装变更卡；
- 准备或修订生成计划。

Agent 没有批准或直接提交 GPU 的工具。公开输出由 LlamaIndex structured output 归一化，前端只显示
最终 Markdown、检索证据、工具调用摘要和审批卡，不显示模型 scratchpad。

HTTP 请求共享本应用的 AgentEngine；不同应用不共享运行任务。每次重试取得新的执行权限，
前一次尝试的工具和事件回调在停止、超时或结束后永久失效。请求取消或服务关闭会中断所属任务，
释放会话以便继续提问。消息去重、运行互斥和会话计数在 SQLite 写事务内更新。

事件按会话和序号建立索引，SSE 只读取游标后的分页；重连支持 `Last-Event-ID`，空闲时发送注释心跳。
会话快照返回最近 200 条事件，并保留服务端序号顺序；更早的事件仍可通过 SSE 游标读取。
模型错误、公开回复和事件会先脱敏再持久化；流式文本在分块前处理，避免长密钥被切成多个片段后泄露。

前端 `AgentSession` 同步阻止重复提交、串行切换会话角色，关闭后使旧请求和流回调失效。
事件先去重再更新文本与界面；请求失败也重新读取持久化消息。只有确认未写入时才恢复输入，
不自动重发结果不确定的请求。关闭助手界面不会取消已经批准的制作任务。

角色偏好与角色 ID 在一次状态更新中切换；模板写入会使分页缓存失效，旧请求不能重新填入缓存。
工作台的同键查询复用请求，快照按角色隔离，切换或关闭时取消读请求；隐藏页暂停轮询，恢复可见后刷新。
快照和在线能力每 5 秒刷新，姿态目录缓存 5 分钟；写入成功后使相关查询失效。查询和写入均不自动重试。
制作提交日志独立于可选偏好：
保存恢复所需的原始请求失败时，不发起生成提交。

前端区分两种意图：

- **分步制作**：修改可复用角色、服装、姿态或表情，先形成工作台变更卡。
- **单张创作**：使用当前身份准备一次性生成计划，不修改角色库。

## 检索

RAG 是 Agent 的证据工具，不负责替 LLM 做最终分类或自动改写角色。

- Qwen3 Embedding 查询 Qdrant 中的模板与 Danbooru Wiki 数据。
- Wiki 名称点和正文 chunk 最终按 canonical `source_id` 聚合。
- 中文整句可通过本地受控词表追加英文 canonical tag 查询，再做 source-level RRF。
- 组合查询保留整句向量结果，并只对强连接词拆出的正向概念做轮询融合。
- 否定条件不会当作向量距离处理；无法确定的排除项以 warning 交给 LLM 判断。
- 通用 cross-encoder reranker 实测降低指标，当前实现已删除。

默认编码器配置为 Qwen3-Embedding-0.6B。更换模型、维度或索引前，使用独立冻结的 holdout 验证，
再显式发布 alias。机器上的 alias 状态、试验分数和原始报告属于运行记录；维护入口见 [RAG 文档](RAG.md)。

检索后端随应用复用，读写两端使用同一套资源初始化与关闭逻辑。每次索引操作重新检查 alias，
避免长期存活的对象沿用切换前的验证结论；单次读写固定使用该次校验的物理 collection，防止编码期间的
alias 或 manifest 切换改变操作目标。编码器使用本应用的设备、线程数和查询指令配置；关闭应用
会释放已加载资源，不为关闭操作额外建立连接或加载模型。

## Anima 提示词

画师风格、固定正面和固定负面是运行时设置，不属于服装模板。正面内容按以下顺序编译：

```text
固定正面 → 人数 → 角色 → 作品 → 画师风格 → 服装/通用/构图 tags → 自然语言 captions
```

当前正式服装库为 50 套精选模板。模板保存 canonical tags、两句 garment caption 和明确排除项；
缩略图可为空。旧的 430 套上游服装没有继续作为产品目录，角色模板仍保留。

## 审批边界

```text
draft → awaiting_approval → queued → running → succeeded / failed
```

- 工作台变更卡批准后才会写入可复用角色或服装。
- 生成计划批准时冻结 revision、内容 hash、来源图片 SHA256、工作流和参数绑定摘要。
- worker 只执行授权记录中列出的 job，且再次校验冻结内容。
- 生成成功不等于选用；候选结果还需要单独选择。
- ComfyUI 离线时允许浏览、检索和准备计划，但不会自动启动推理。

## 验收范围

- 使用真实 OpenAI-compatible 模型完成长会话、工具选择和异常恢复验收。
- 服装缩略图和提示词策略需要真实图片质量验收。
- 检索模型切换需要独立审校并冻结的评估集。
- 完成 Agent 驱动的身份→服装→姿态→表情→透明输出端到端人工验收。

## 验证

```bash
make check
```

修改 API 或共享目录后先执行 `make contracts`。后端检查导出契约是否漂移；前端独立检查
生成类型与契约一致，不安装 Python。完整响应模型只覆盖上文列出的工作台接口，新增类型应从后端模型扩展。

单元测试不替代真实模型响应质量或生成图片质量验收。
