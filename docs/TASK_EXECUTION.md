# 任务投递、执行与恢复

API 与 Worker 为独立进程，同机共享 SQLite WAL 和资产目录。SQLite 保存任务、批准快照、投递记录和结果，
RabbitMQ 只传递 `job_id` 与投递 `generation`。消息不携带模型参数、提示词或资产路径。

## 事务与进程

```text
用户确认 → API 校验 → SQLite 事务：授权/批次 + jobs + snapshot + outbox
                                     ↓
独立 Worker 中的 relay → RabbitMQ publisher confirm → 标记 outbox 已发布
                                     ↓
RabbitMQ 消费者 → SQLite 持久化 received → 手动 ACK
                                     ↓
独立 Worker 中的 executor → 提交 CAS → ComfyUI → 核对 history → 保存结果
```

- Agent 的授权、工作台批次和兼容 `/jobs` 入队都在原事务中写入 outbox；回滚不会遗留可执行消息。
- 网络发布在事务外完成；只有收到确认才更新 `published`。提交数据库后消息服务离线，任务仍为排队状态。
- 发布失败按指数退避重试，间隔上限 60 秒，保留数据库意图。确认丢失可能导致重复消息；接收记录按任务和
  generation 去重，不能把旧代次消息用于新一次手动重试。
- 新工作台和兼容接口任务冻结场景、角色、提示词设置、工作流/字段绑定和输入资产摘要；Agent 沿用批准快照。
  执行时校验输入文件 SHA256。升级前旧任务保留既有执行语义，不把升级时的内容宣称为用户已批准快照。

## 单 GPU 与长任务

队列为持久化 quorum queue，消息使用 persistent delivery mode；启用 single active consumer、prefetch=1、
手动 ACK、publisher confirms 和 mandatory routing。单节点开发配置提供持久化，不提供多节点容灾。

ACK 表示“收到数据库”，不是“生成完成”。消费者只做短数据库事务，不持有消息等待 GPU 完成。因此长任务
不依赖放大 RabbitMQ consumer timeout；断开连接前未确认的消息由 RabbitMQ 重投，确认后的任务由数据库恢复。
消费者写数据库最多尝试三次；永久无效消息、耗尽接收重试的消息进入死信队列。

执行进程同时持有数据目录 `worker.lock` 和 `AIGC_GPU_LOCK`。同一 GPU 的实例必须配置相同 GPU 锁路径，
部署在同一服务器、相同用户下。数据库事务还要求当前没有 submitting/running/recovering/submission_uncertain
任务，才能将一个 queued 任务改为 submitting。发布和接收可以持续进行，GPU 执行始终串行。

停止或强杀 Worker 不会全局中断 ComfyUI。下一进程先核对活跃任务，保留原 prompt ID 与提交意图，
完成已有任务后才执行下一项。不根据消息 redelivered 标志决定是否重新推理。

## 状态与重试

| 当前状态/事件 | 后续行为 |
| --- | --- |
| queued，尚未收到 RabbitMQ 消息 | 保持排队，outbox 等待确认 |
| queued，持久化接收完成 | 复核快照、输入和模型；空闲时 CAS 到 submitting |
| 提交前的网络连接错误 | 最多 3 次执行尝试，指数退避；耗尽后 failed，允许显式重试 |
| submitting，成功取得 prompt ID | running |
| 提交超时、断线或成功响应无法解析 | submission_uncertain，不自动重发 |
| Worker 重启发现 submitting/running | 按 prompt ID 或 aigc_job_id 查询 history/queue |
| ComfyUI 暂不可达或返回无法核对的响应 | recovering，保留提交意图并继续核对 |
| 提交已完成，但找不到 prompt/history/queue | submission_uncertain，阻止后续 GPU 任务，等待人工核对 |
| history 明确成功且输出通过检查 | succeeded |
| history 明确失败或冻结输入验证失败 | failed；重新准备计划，不开放自动推理重试 |
| 人脸选择需要修改 | needs_correction |
| queued 被取消 | 原子变为 cancelled；并发领取已发生时返回 409 |

`POST /api/v1/jobs/{id}/retry` 接收 `{ "generation": 0 }`。仅 failed、标记为安全重试、无 prompt ID 的任务允许重试；
在同一事务中递增代次、清空接收标志并写新 outbox。重复按钮请求不会增加额外尝试。
提交意图一旦写入，不通过此接口清除。执行失败会向 `<queue>.dead` 发布审计消息；这些消息不自动重新执行。

ComfyUI 本身没有原子“按幂等键提交”的协议，所以无法消除“已发送但无响应且历史被清除”的信息缺口。
本实现宁可停在待核对，也不会承诺 exactly-once 推理。人工核对必须保留原任务和授权记录，不能直接把
submission_uncertain 改回 queued。接收阶段若数据库持续不可写，消息保留在死信队列，恢复后需人工核对并重新投递
原 ID/代次；不要用新任务绕过不确定的提交。

## 启动

在服务器独立开发目录安装锁定依赖。API 和 Worker 使用同一份配置；以下命令各占一个终端：

```bash
uv sync --locked --group dev
bash scripts/run.sh
uv run --locked python -m aigc.worker_main
```

默认 `AIGC_EXECUTION_MODE=local`：独立 Worker 扫描持久化任务，不连接 RabbitMQ。
`rabbitmq` 模式只执行已收到消息的任务。模式绑定在数据库，配置冲突时启动失败；现阶段不支持在线切换，
开发时使用不同的数据目录。不能同时启动旧版内嵌 Worker 和新版消费者。

RabbitMQ 开发环境使用 [Compose 配置](../deploy/rabbitmq.compose.yml)：

```bash
# 在当前 shell 设置本地专用账号；不要提交账号或 config.env。
export AIGC_RABBITMQ_USER=caster
read -rs -p 'RabbitMQ password: ' AIGC_RABBITMQ_PASSWORD
export AIGC_RABBITMQ_PASSWORD
docker compose -p caster-dev -f deploy/rabbitmq.compose.yml up -d
```

在本地配置文件设置：

```text
AIGC_EXECUTION_MODE=rabbitmq
AIGC_DATA_DIR=data/rabbitmq-dev
AIGC_RABBITMQ_URL=amqp://<user>:<url-encoded-password>@127.0.0.1:5672/
AIGC_RABBITMQ_QUEUE=caster.gpu0
AIGC_GPU_LOCK=/tmp/caster-gpu-0.lock
```

端口固定、仅回环监听；通过 SSH 隧道访问。不同数据库使用不同队列名，同一 GPU 使用相同锁路径。
Compose 数据卷支持 broker 重启；不要执行 `down -v` 清除仍需保留的消息。

## 健康检查与日志

`GET /api/v1/health` 的 `status=ok` 只表示 API 可响应；还需检查：

- `worker_alive`：独立进程最近 15 秒内有心跳；心跳每 3 秒写入，不等待 GPU 完成。
- `execution_mode`：当前配置模式。
- `broker_connected`：RabbitMQ 最近连通状态；local 模式为 null。
- `outbox_pending`：尚未确认的消息数，包括退避中的记录；local 模式为 0。

HTTP 返回 `X-Request-ID`；outbox 保存同一 request_id，AMQP message_id 为 outbox ID，correlation_id 为 request_id。
Worker 的 outbox_confirmed、inbox_committed 和 job_state 日志可按这些 ID 关联。不记录 AMQP URL 或模型凭据。

任务列表和角色快照返回 delivery 代次、尝试数与 retryable。`GET /api/v1/jobs/events` 复用现有 SSE 帧实现，
支持 Last-Event-ID、增量游标与空闲心跳；任务状态与事件在同一 SQLite 事务提交。前端收到事件刷新快照，
原轮询保留用于进度与连接恢复。前端只对服务端允许的失败任务展示重试按钮。

## 故障测试

默认离线测试不会连接真实模型或 GPU：

```bash
uv run --locked pytest -q
```

需要单独启动可丢弃的 RabbitMQ，再明确提供测试连接：

```bash
AIGC_TEST_AMQP_URL='<isolated-amqp-url>' uv run --locked pytest -q tests/test_broker_integration.py
AIGC_TEST_AMQP_URL='<isolated-amqp-url>' \
AIGC_TEST_RABBITMQ_CONTAINER='<caster-queue-test-container>' \
uv run --locked pytest -q tests/test_worker_process.py
```

第二条会停止并重启明确指定的测试容器，不能指向正式 broker。测试启动真实 API/Worker 子进程和模拟 ComfyUI，
执行 SIGKILL、提交响应损坏、消息服务停机与恢复；不启动 ComfyUI 或调用模型。未配置 RabbitMQ 时集成用例明确跳过。

实现参考：[RabbitMQ confirms](https://www.rabbitmq.com/docs/confirms)、
[消费者与确认超时](https://www.rabbitmq.com/docs/consumers)、
[死信处理](https://www.rabbitmq.com/docs/dlx)、[aio-pika](https://docs.aio-pika.com/quick-start.html)。
