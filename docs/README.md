# 文档入口与阶段状态

## 规范路径

- `Phase_1/`：第一阶段已经实施的 PRD、Spec、接口语义、验收、协作记录和使用手册。内容用于解释现有 R1—R5 代码，不作为第二阶段新增需求。
- `Phase_2/`：第二阶段已确认的设计交接包，包含 P2.0—P2.4 范围、契约增量、选型、验收、协作规则和模板。未落地能力必须标记为 `partial`、`stub` 或 `missing`。
- 根目录 `tasks/`：第一阶段历史任务书。第二阶段任务入口在 `Phase_2/tasks/`。

目录名大小写是契约的一部分。代码、PR 和任务说明统一使用 `docs/Phase_1/` 与 `docs/Phase_2/`，不得再新增 `docs/phase1/`、`docs/phase2/`，也不得把阶段文档散放回 `docs/` 根目录。

## Phase 1 基线状态

Phase 1 的自动化冻结候选仍以 `main@c7642185458a37719ca210a08b7cd8e18f3e129a` 记录。此后 PR #18、#19 已继续进入主线；当前远端 `main@128f2c7e25a3a9e9745ded1da7742ff556f31e2b` 已包含 Phase 2 Agent 基线与 Registry。该技术演进不代替 Phase 1 人工冻结门槛，也不把新主线提交追认为已签核的 Phase 1 冻结点。

该提交上的 141 项后端测试、30 条 fixture/4 项毛利基线检查、契约生成零漂移、前端干净安装、28 项前端测试、生产构建和真实本地 HTTP 冒烟均通过；PR17 对应的 `main` GitHub Actions 也已成功。当前状态仍是 `candidate_pending_manual`，不是正式 `frozen`：可见浏览器、报告下载、关键结论支持性、团队财务签核和第二位开发者独立复现仍必须由实际执行者补充证据。

详细结果和未完成项见 `Phase_1/README.md` 与 `../validation/Phase1冻结验收记录.md`。

## Phase 2 分支入口

团队已从 `main@128f2c7e25a3a9e9745ded1da7742ff556f31e2b` 建立共享 `develop`，后续 Phase 2 短期分支从该分支创建并回到 `develop`。建立分支这一事实不代签 Phase 1 财务签核、独立复现或浏览器验收；正式冻结字段仍以验收记录为准。完整顺序见 `Phase_2/docs/07_剩余任务执行计划.md`。
