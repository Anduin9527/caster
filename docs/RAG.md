# 检索与索引维护

模板的精确匹配与 BM25 可直接运行。语义检索是可选能力：Qwen3 Embedding 生成向量，Qdrant 检索
模板与 Danbooru Wiki，正文目录补齐内容和来源；Agent 根据证据选择标签并处理否定条件。

## 环境与配置

在目标服务器的独立 RAG 工作区保存模型、输入、索引清单和报告。运行 API 的 Python 环境需能导入
`qdrant-client`、`torch` 与 `transformers`；只有实际使用语义检索时才加载编码器。
基础应用的 `uv.lock` 不安装 GPU 推理包。可参考 `scripts/rag_pyproject.toml` 准备匹配设备的环境，
在该工作区生成并保留自己的依赖锁；该文件的 CUDA 12.6 示例不适用于所有驱动。

`scripts/rag_qdrant_config.yaml` 提供回环监听示例，存储路径相对于启动 Qdrant 时的工作目录。
离线脚本默认从当前源码目录导入 `aigc`；将脚本复制到独立工作区时，用 `AIGC_PACKAGE_ROOT` 指向源码。

`config.env` 中 `AIGC_RAG_DIR` 留空表示语义检索未配置。启用时，模型 key、输出维度、查询指令、
最大长度和索引版本必须与发布清单一致，完整字段见根目录 `config.env.example`。
编码器默认使用 CPU；选择 GPU 时需显式设置 `AIGC_RAG_DEVICE`。

`GET /agent/index/status` 检查配置与已发布索引是否匹配，以及模板增量同步状态。检索不可用时给出原因。
名称精确解析依赖经过验证的正文名称表，准备好后再开启 `AIGC_RAG_EXACT_RESOLVER`。

## 维护顺序

1. `rag_snapshot_templates.py` 只读导出业务模板；`prepare_rag_wiki.py` 校验输入摘要并生成 Wiki chunk/name 数据。
2. `verify_rag_wiki.py` 验证语料；`rag_build_bodies.py` 构建正文与名称目录。
3. `rag_build_index.py` 编码并写入指定 collection，同时保存向量缓存和索引清单。
4. `rag_verify_index.py` 独立校验输入摘要、点数、payload 和抽样向量。
5. 对冻结评估集运行 `rag_eval_live_backend.py`，检查来源命中、覆盖率、排除项冲突与延迟。
6. 经明确选择后使用 `rag_publish_alias.py` 发布 alias；支持 `--dry-run` 先查看验证结果。

构建只接受未被任何 alias 发布的 collection，已发布版本应使用新名称重建。`--skip-wiki`
或 `--skip-templates` 的清单只验证本次实际构建的集合，发布时保留其他 alias；空清单、
不完整语料、无抽样证据或损坏的向量缓存都不能通过。验证以只读方式打开缓存，资源在失败时也会释放。

每个脚本通过 `--help` 提供实际参数。所有输入、模型、缓存、评估集与报告放在忽略目录中，
不将单次扫参脚本或评估流水写入公共文档。

## 可重复评估

在已准备检索环境的服务器上，使用正式的 RetrievalService 路径评估，不启动 ComfyUI：

```bash
python /path/to/caster/scripts/rag_eval_live_backend.py \
  --package-root /path/to/caster \
  --queries /path/to/corpus/frozen-holdout.json \
  --wiki-names /path/to/corpus/wiki-names.jsonl.gz \
  --out /path/to/caster/data/reports/retrieval.json
```

评估文件包含 `queries` 数组；每项包含 `id`、`query` 和 `expected_source_ids`，也可使用
`expected_tags`、`required_tags`、`forbidden_tags`。使用标签时必须提供与语料对应的 `--wiki-names`。
每次比较保持同一份冻结数据、相同标签来源与参数，并记录模型 commit 和索引指纹。
仓库不附带未经审校的私有 pilot，也不把小样本结果声明为通用质量保证。
