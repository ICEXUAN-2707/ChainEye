# 文档入口与阶段状态

## 规范路径

- `Phase_1/`：第一阶段已经实施的 PRD、Spec、接口语义、验收、协作记录和使用手册。内容用于解释现有 R1—R5 代码，不作为第二阶段新增需求。
- `Phase_2/`：第二阶段已确认的设计交接包，包含 P2.0—P2.4 范围、契约增量、选型、验收、协作规则和模板。未落地能力必须标记为 `partial`、`stub` 或 `missing`。
- 根目录 `tasks/`：第一阶段历史任务书。第二阶段任务入口在 `Phase_2/tasks/`。

目录名大小写是契约的一部分。代码、PR 和任务说明统一使用 `docs/Phase_1/` 与 `docs/Phase_2/`，不得再新增 `docs/phase1/`、`docs/phase2/`，也不得把阶段文档散放回 `docs/` 根目录。

## Phase 1 基线状态

截至 2026-10-08，远端 `main` 为 `c7642185458a37719ca210a08b7cd8e18f3e129a`。PR #8、#12—#17 已合并；Vite 锁定为 `7.3.7`，PR17 补齐诊断比较、数据集身份、PDF CJK 字体发现/子集嵌入及相应回归测试。

该提交上的 141 项后端测试、30 条 fixture/4 项毛利基线检查、契约生成零漂移、前端干净安装、28 项前端测试、生产构建和真实本地 HTTP 冒烟均通过；PR17 对应的 `main` GitHub Actions 也已成功。当前状态仍是 `candidate_pending_manual`，不是正式 `frozen`：可见浏览器、报告下载、关键结论支持性、团队财务签核和第二位开发者独立复现仍必须由实际执行者补充证据。

详细结果和未完成项见 `Phase_1/README.md` 与 `../validation/Phase1冻结验收记录.md`。

## Phase 2 分支入口

Phase 2 当前只从稳定 `main` 开展 Agent 基线、Registry、Orchestrator、MCP 与原生复现的独立短期 PR；不因此代签 Phase 1 人工门槛或伪造正式冻结。共享 `develop` 仅在团队决定启用并得到唯一冻结提交后建立一次。完整顺序见 `Phase_2/docs/07_剩余任务执行计划.md`。
