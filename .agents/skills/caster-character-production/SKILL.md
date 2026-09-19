---
name: caster-character-production
description: 通过自然语言描述制作角色资产：匹配模板、规划流程、生成原图/换装/动作/表情/抠图
---

# CASTER 角色资产制作

通过自然语言描述制作角色资产的操作指南。告诉 Agent 去哪里找配置、如何串联现有能力、什么结果才算完成。

## 触发条件

用户用自然语言描述角色制作需求时触发：

- "用约尔的角色模板，换成女仆装，生成敬礼、格斗戒备和抱膝三个动作"
- "给初音未来生成踢腿动作的生气表情，导出透明 PNG"
- "用 Kiana 角色，生成原图和三套服装的对比"

不触发：仅查询模板、修改代码、运维操作。

## 从项目配置发现能力

### 1. 读取服务配置

```bash
# 查看配置示例
cat config.env.example

# 检查服务状态
curl http://127.0.0.1:8189/health
curl http://127.0.0.1:8189/production/capabilities
```

**关键信息**：
- 后端地址：默认 `http://127.0.0.1:8189`
- 数据目录：环境变量 `AIGC_DATA_DIR` 或默认 `data/local-dev`
- ComfyUI 状态：`capabilities.generation_online`
- 支持的输入：`capabilities.pose_input` (pose_studio_3d)

### 2. 查询可用模板和预设

```bash
# 角色模板
curl "http://127.0.0.1:8189/prompt-templates?kind=character&q=初音未来"

# 服装模板
curl "http://127.0.0.1:8189/prompt-templates?kind=outfit&q=女仆装"

# 姿态预设
curl "http://127.0.0.1:8189/production/pose-presets"
```

**不要硬编码**：
- 模板 ID（如 `hub-character-miku`）
- 预设编号（如 `105`）
- 模型参数、采样步数

**从查询结果中获取**：
- 模板的 `id`、`name`、`trigger`、`tags`
- 预设的 `id`、`name`、`preview_url`

### 3. 理解现有工作流

读取 `workflows/bindings.json` 和 `workflows/*.api.json` 了解：
- 可用的工作流类型：`sprite`, `outfit`, `pose`, `expression`, `matte`
- 各工作流的输入参数
- 不要修改工作流的采样参数

## 执行流程

### 阶段 1：理解需求

从用户描述中提取：
- 角色名称
- 服装描述（可选）
- 动作描述（可选）
- 表情描述（可选）
- 尺寸要求（可选，默认 1024x1536）
- 是否导出透明 PNG

**决策规则**：
- 只有明显影响结果的歧义才询问
- 未指定的参数沿用项目默认
- 找不到精确匹配时，展示候选项供用户选择

### 阶段 2：查询并匹配

调用 API 查询模板和预设：

```bash
# 查询角色模板（支持中英文）
curl "http://127.0.0.1:8189/prompt-templates?kind=character&q=${角色查询}"

# 如果有多个结果，展示给用户选择
# 如果没有结果，告诉用户并停止
```

**匹配约束**：
- 动作必须匹配已有姿态预设（Pose Studio），不能用纯文字描述生成姿态
- 服装可以是模板库中的，也可以是用户自定义文字描述

### 阶段 3：创建角色实例

```bash
# 1. 预览角色（可选）
curl -X POST http://127.0.0.1:8189/prompt-templates/preview \
  -H "Content-Type: application/json" \
  -d '{
    "character_template_id": "...",
    "outfit_template_ids": [],
    "character_id": "角色实例ID",
    "include_character_tags": true
  }'

# 2. 实例化角色
curl -X POST http://127.0.0.1:8189/prompt-templates/instantiate \
  -H "Content-Type: application/json" \
  -d '{
    "character_template_id": "...",
    "character_id": "唯一ID（如 miku-001）",
    "include_character_tags": true
  }'
```

### 阶段 4：创建服装版本（如果需要）

```bash
curl -X POST http://127.0.0.1:8189/production/characters/${角色ID}/outfits \
  -H "Content-Type: application/json" \
  -d '{
    "id": "outfit-maid",
    "tags": ["maid outfit", "white apron", "..."],
    "description": "女仆装",
    "name": "女仆装",
    "parent_id": null
  }'
```

###阶段 5：按流程生成

**流程顺序**（必须严格遵守）：
```
身份原图 (identity)
  └→ 换装 (outfit)
       └→ 动作 (pose)
            └→ 表情 (expression)
                 └→ 抠图 (matte)
```

**关键约束**：

1. **尺寸继承**
   - 只有原图 (identity) 可指定 `canvas_preset`
   - 后续阶段自动继承源图尺寸

2. **动作使用换装图**
   - 动作编辑 (pose) 必须从换装图 (outfit) 生成
   - 不能直接从原图生成动作

3. **表情独立分支**
   - 所有表情从**同一张中性姿态图**并行生成
   - 不是从"开心表情"生成"生气表情"
   - 避免表情累积效应

4. **选择与审批**
   - 每个阶段必须选择一张图片才能进入下一步
   - 首次选择需要 `approve: true`
   - 使用 `PUT /production/characters/{id}/selection`

#### 生成身份原图

```bash
curl -X POST http://127.0.0.1:8189/production/characters/${角色ID}/batches \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "unique-key-identity",
    "expected_revision": 0,
    "role": "identity",
    "canvas_preset": "1024x1536",
    "candidates": [
      {"seed": 9527},
      {"seed": 9528},
      {"seed": 9529}
    ]
  }'
```

**等待完成**：
```bash
# 轮询状态
curl "http://127.0.0.1:8189/production/snapshot?character_id=${角色ID}"

# 检查 jobs 中的 state 字段
# - succeeded: 成功
# - failed: 失败，查看 error
# - needs_correction: 需修正（如无脸、多脸）
```

**选择结果**：
```bash
curl -X PUT http://127.0.0.1:8189/production/characters/${角色ID}/selection \
  -H "Content-Type: application/json" \
  -d '{
    "expected_revision": 0,
    "stage": "identity",
    "asset_id": "...",
    "approve": true
  }'
```

#### 生成换装图（如果需要）

```bash
curl -X POST http://127.0.0.1:8189/production/characters/${角色ID}/batches \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "unique-key-outfit",
    "expected_revision": 1,
    "role": "outfit",
    "candidates": [
      {"outfit_id": "outfit-maid", "seed": 9527}
    ]
  }'
```

#### 生成动作图（如果需要）

**先保存姿态预设**：
```bash
# 查询预设 ID
curl "http://127.0.0.1:8189/production/pose-presets" | jq '.[] | select(.name | contains("敬礼"))'

# 保存预设（指定原生尺寸）
curl -X POST "http://127.0.0.1:8189/production/pose-presets/105?width=1024&height=1536"
```

**生成动作**：
```bash
curl -X POST http://127.0.0.1:8189/production/characters/${角色ID}/batches \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "unique-key-pose",
    "expected_revision": 2,
    "role": "pose",
    "candidates": [
      {"pose_id": "pose-id", "seed": 9527}
    ]
  }'
```

#### 生成表情（如果需要）

**约束**：
- 表情描述要克制，不加强调权重
- 默认使用自动脸部检测（`face_region: null`）
- 如果失败（`needs_correction`），查看错误并提供 `face_region`

```bash
curl -X POST http://127.0.0.1:8189/production/characters/${角色ID}/batches \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "unique-key-expression-1",
    "expected_revision": 3,
    "role": "expression",
    "candidates": [
      {"expression": "happy, smiling", "seed": 9527}
    ]
  }'
```

**多个表情**：
```bash
# 表情 2（同样依赖 revision 3，不是 4）
curl -X POST http://127.0.0.1:8189/production/characters/${角色ID}/batches \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "unique-key-expression-2",
    "expected_revision": 3,
    "role": "expression",
    "candidates": [
      {"expression": "angry, frowning", "seed": 9527}
    ]
  }'
```

#### 生成透明抠图（如果需要）

```bash
curl -X POST http://127.0.0.1:8189/production/characters/${角色ID}/batches \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "unique-key-matte",
    "expected_revision": 3,
    "role": "matte",
    "candidates": [
      {"asset_id": "要抠图的资产ID"}
    ]
  }'
```

### 阶段 6：验证与交付

#### 验证结果

```bash
# 获取完整状态
curl "http://127.0.0.1:8189/production/snapshot?character_id=${角色ID}"
```

**检查项**：
1. **图片实际生成**
   - `jobs[].state == 'succeeded'`
   - `jobs[].outputs` 包含资产 ID

2. **来源正确**
   - `assets[].scene_spec_id` 对应正确的 `scene_spec`
   - `assets[].parent_asset_id` 指向正确的源图

3. **尺寸符合要求**
   - 原图：用户指定或默认 1024x1536
   - 后续阶段：继承源图尺寸

4. **透明通道**
   - `role == 'reference'` 的资产 `mode == 'RGBA'`

5. **表情像素不变性**（如果有表情）
   - 查看 `validation` 记录
   - `canvas_unchanged`, `outside_mask_unchanged`, `original_asset_preserved` 都为 true

#### 下载资产

```bash
# 下载单个资产
curl "http://127.0.0.1:8189/assets/${asset_id}/file" -o output.png

# 下载完整清单
curl "http://127.0.0.1:8189/production/characters/${角色ID}/manifest" -o manifest.json
```

#### 组织交付

根据用户需求：
- **对比拼图**：使用 Pillow 生成（换装一行 / 动作一行 / 表情一行）
- **原图 ZIP**：打包所有生成结果
- **任务清单**：JSON 格式，包含选择历史和输入输出关系

## 错误处理

### 常见错误状态

| 状态 | 含义 | 处理方式 |
|-----|------|---------|
| `needs_correction` | 脸部检测失败（无脸、多脸） | 查看 `error`，提供 `face_region` 重试 |
| `failed` | 任务失败 | 查看 `error` 并报告用户 |
| `submission_uncertain` | 提交结果不确定 | 查询 ComfyUI 历史和队列，人工核对 |

### 冲突处理

```json
// 409 Conflict
{
  "detail": "Selection changed; refresh before selecting"
}
```

**处理**：重新获取 `snapshot`，使用最新的 `revision`。

### 恢复中断任务

```bash
# 查询现有批次
curl "http://127.0.0.1:8189/production/snapshot?character_id=${角色ID}"

# 检查 batches 中的 job_ids
# 使用相同的 idempotency_key 不会重复提交
```

## 参考资料

### 工作流说明

**sprite（角色原图）**：
- 输入：角色特征 + 服装 + 风格
- 输出：RGB 图片（`role='original'`）
- 采样：Euler/Beta, 36 steps, CFG 4.0

**outfit（换装）**：
- 输入：源图 + 新服装描述
- 输出：RGB 图片
- 重绘强度：denoise 0.8

**pose（动作）**：
- 输入：源图 + Pose Studio 渲染图
- 输出：RGB 图片
- 模型：Qwen Image Edit 2511 + Pose LoRA

**expression（表情）**：
- 输入：源图 + 表情描述 + 可选脸部区域
- 输出：编辑后图片 + 掩码
- 约束：掩码外像素不变

**matte（抠图）**：
- 输入：源图
- 输出：RGBA 图片（`role='reference'`）
- 模型：BiRefNet

### 画布预设

```bash
# 查看可用预设
cat integrations/canvas-presets.json
```

常用预设：
- `1024x1536`（默认）
- `768x1024`
- `1536x1024`

### API 文档

```bash
# 查看完整 API 文档
open http://127.0.0.1:8189/docs
```

主要端点：
- `/prompt-templates` - 模板查询和管理
- `/production/characters/{id}/batches` - 提交批次
- `/production/characters/{id}/selection` - 选择结果
- `/production/snapshot` - 获取完整状态
- `/production/pose-presets` - 姿态预设
- `/assets/{id}/file` - 下载资产

## 注意事项

1. **不覆盖旧资产**
   - 每个阶段生成新资产，不修改已有的
   - 切换选择保留旧资产

2. **提交结果不确定时**
   - 先查询 ComfyUI 历史：`GET /comfyui/history`
   - 不要自动重新提交

3. **表情默认克制**
   - 不加强调权重（如 `(happy:1.5)`）
   - 描述简洁（如 "happy, smiling"）

4. **区分实验选择与生产批准**
   - 实验：生成多个候选，选择最佳
   - 生产批准：`approve: true`，用于后续工作流

5. **幂等提交**
   - 使用唯一的 `idempotency_key`
   - 相同 key 不会重复提交

6. **监控进度**
   - 长时间运行的任务定期轮询 `snapshot`
   - 不要过于频繁（建议 2-5 秒间隔）
