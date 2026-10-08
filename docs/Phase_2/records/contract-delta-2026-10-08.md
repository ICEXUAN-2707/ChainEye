# Agent Kernel 与 MCP 契约影响基线

核查日期：2026-10-08
当前 HTTP/OpenAPI 版本：`0.4.0`。

## 本分支

`chore/p2-agent-baseline` 仅更新计划与核查记录，不修改路由、DTO、领域模型、数据库迁移、OpenAPI、JSON Schema 或生成 TypeScript。执行生成命令后必须保持 `contracts/**` 与 `frontend/src/api/generated.ts` 零漂移。

## 后续增量

|阶段|复用或新增|HTTP 契约|持久化影响|兼容原则|
|---|---|---|---|---|
|Agent Registry|把现有 6 个 `RunTools` 迁移到统一 ToolRegistry；Prompt 文件化；新增 SkillRegistry|无变化|无迁移|保留工具名、输入语义、错误语义和事件内容|
|Agent Orchestrator|把 `RunExecutionService` 的隐式步骤迁移为显式有向图和节点规范|无变化|优先复用现有 Run 与 event 字段；如需元数据再单独提迁移 PR|旧 Run 可读、回放语义不变、失败不伪成功|
|MCP MVP|新增独立 stdio 协议入口、resources、prompts 元数据和只读 tools|不把 MCP 伪装成 HTTP 路由|无迁移或只读查询|MCP 与内部 Agent 共用 ToolRegistry，不复制业务实现|
|原生复现与日志|新增 CLI、JSONL 日志、trace 导出与脱敏|无变化|日志在 `.runtime/`，不得提交|日志不含密钥、Authorization、完整环境或无界原文|
|第二企业/OCR|待前述关口完成后单独设计|预计有契约增量，必须先写变更理由|预计新增 profile/job/page artifact 相关存储|从后端单一来源生成，旧 CATL 快照保持可读|

## MCP MVP 暴露面

MCP 使用 stdio，不提供 HTTP/SSE、公网访问或身份认证承诺。首版只暴露读取型能力：

- Resources：Dataset version、Evidence、Run trace、Report、Skill metadata。
- Tools：`get_facts`、`get_evidence`、`search_documents`、`get_run_trace`、`get_report`。
- Prompts：只发布版本、用途、输入要求和内容哈希等元数据；Prompt 正文仍由运行时 Registry 管理。

内部 Agent 继续使用全部 6 个工具。`compute_financials`、`compute_scenario`、`validate_claims` 暂不作为 MCP 外部工具发布，直到上下文绑定、幂等和写入边界有独立审查。MCP 不提供任意 shell、SQL、文件路径、网络请求或人工 `verified` 写入。

## 需要共同评审的未来变化

只有当后续节点/Skill 元数据必须进入 HTTP Report 或 Run DTO 时，才提升 OpenAPI 版本并同步后端模型、生成物、接口文档和测试。不能为了前端展示另建平行 DTO，也不能手改生成文件。
