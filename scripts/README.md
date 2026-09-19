# Scripts 目录说明

## 部署与运维
- `service.py` — Linux 服务管理（启动/停止/重启/状态）
- `run.sh` — 快速启动脚本（开发环境）

## 数据导入与缓存
- `import_anima_hub.py` — 从上游导入 Anima 模板到数据库
- `cache_template_previews.py` — 缓存模板配图（缩略图和预览图）
- `cache_pose_studio.py` — 渲染并缓存 Pose Studio 姿态库
- `map_template_names.py` — 构建模板名称的中文映射

## 工作流验证
- `probe_workflow.py` — 提交工作流并检查输出
- `baseline.py` — 生成基准图片（回归测试用）
- `verify_pixels.py` — 验证图片像素不变性
- `compare_anima.py` — 对比 Anima 参数变化
- `compare_edits.py` — 对比编辑方法差异

## 验收与实验
- `acceptance_snapshot.py` — 生成验收测试快照
- `continue_acceptance.py` — 继续未完成的验收测试
- `review_expressions.py` — 审阅表情生成结果
- `export_samples.py` — 导出样例图片
- `export_ui.py` — 导出前端静态资源

## 特定功能探测
- `occlusion_probe.py` — 测试遮挡修正（手部、头发）
- `reference_probe.py` — 测试参考图编辑方法
- `restart_probe.py` — 测试 ComfyUI 重启后的恢复

## 浏览器辅助
- `pose-studio-render.html` — Pose Studio 浏览器渲染页面（配合 `render_pose_studio.py`）
- `render_pose_studio.py` — 调用浏览器渲染 Pose Studio 人偶

## 依赖下载

## 核心 API 入口
- `aigc.py` — 后端 API 启动入口（通常通过 uvicorn 调用）

---

## 使用场景

### 初次部署
```bash
uv run python scripts/import_anima_hub.py
uv run python scripts/cache_template_previews.py
uv run python scripts/cache_pose_studio.py
```

### 日常开发
```bash
bash scripts/run.sh  # 启动后端
```

### 生产运维
```bash
uv run python scripts/service.py start   # 启动服务
uv run python scripts/service.py status  # 检查状态
uv run python scripts/service.py restart # 重启服务
```

### 回归测试
```bash
uv run python scripts/baseline.py        # 生成基准
uv run python scripts/verify_pixels.py   # 验证不变性
```

### 实验与验收
```bash
uv run python scripts/acceptance_snapshot.py  # 生成验收快照
uv run python scripts/review_expressions.py   # 审阅表情
```

---

## 职责划分建议（待整理）

当前所有脚本平铺在一个目录，未来可考虑按职责拆分：
- `scripts/deploy/` — 部署相关
- `scripts/data/` — 数据导入导出
- `scripts/dev/` — 开发工具
- `scripts/maintenance/` — 运维工具

但由于现有部署脚本绑定了服务器路径，暂不移动。
