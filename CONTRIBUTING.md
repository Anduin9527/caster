# 开发与贡献

CASTER 的源码包含工作台、Agent 与业务状态层；ComfyUI 和检索模型使用独立运行环境。
在目标开发机器上执行以下命令。远端开发时，将源码同步到服务器上的独立目录后再安装、测试和构建，
避免把开发环境写入正在提供服务的部署目录。

```bash
make setup
make check
```

`make check` 运行 Ruff 静态检查与格式校验、仓库文件与文档链接检查、pytest、前端类型检查、
前端测试、Sites 适配测试和生产构建。这些检查无需 GPU、模型密钥或历史图片。
CI 在 Linux 上分别验证后端与前端；前端检查不安装 Python。

日常使用 `make check-backend` 或 `make check-frontend` 检查影响范围，使用 `make format` 格式化 Python。
生产入口仍为 `aigc.api:app`，测试通过 `create_app(config, store=..., comfy=...)` 注入依赖。
pytest 使用临时配置与数据目录，不读取个人模型连接或运行数据库。

## 修改约定

- Agent 编排使用 LlamaIndex `FunctionAgent`；公开输出经过结构化约束，工具只准备变更与计划。
- 变更审批、生成授权、结果选用分别保留。修订计划、工作流或来源图片时必须重新验证冻结内容。
- 数据库格式、接口路径、内部 `aigc` 包、`AIGC_*` 变量和部署入口保持兼容；必要的迁移需提供恢复方案。
- 测试覆盖可观察的行为：审批冲突、幂等重放、断线恢复、事件顺序、掩码外像素不变。
- Python 依赖通过 `uv.lock` 更新，前端依赖通过 `package-lock.json` 更新。第三方节点许可与来源必须保留。

## 什么进入仓库

提交源码、回归测试、通用工作流、脱敏配置示例和稳定主题文档。`docs/images/` 仅保存文档实际引用的展示图。
`scripts/` 保留可重复使用的运维、索引与评估工具。

模型、数据集、SQLite、生成图片、日志、机器专用部署文件、试验扫参脚本和逐日开发记录放在被忽略的
`data/` 等本地目录。运行证据使用 `data/reports/`，实验与旧脚本使用 `data/local-history/`。
不要用新的日期文档复制交接记录。`scripts/check_repository.py` 会检查待提交文件中是否混入这些产物，
并确认公开 Markdown 的本地链接可在干净克隆中解析。

## 真实环境验收

离线测试只能证明代码契约。真实模型对话、检索效果、GPU 生成和图片质量需单独验收，
在报告中说明模型/节点版本、输入、执行结果和质量结论。共享 GPU 上按既有授权串行执行。
构建或测试不应自动启动 ComfyUI、提交生成任务或切换检索 alias。

实现参考：[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)、
[uv 的 GitHub Actions 集成](https://docs.astral.sh/uv/guides/integration/github/)、
[Vite 配置](https://vite.dev/config/)。
