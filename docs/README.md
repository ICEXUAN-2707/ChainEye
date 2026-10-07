# 文档入口与阶段状态

## 规范路径

- `Phase_1/`：第一阶段已经实施的 PRD、Spec、接口语义、验收、协作记录和使用手册。内容用于解释现有 R1—R5 代码，不作为第二阶段新增需求。
- `Phase_2/`：第二阶段已确认的设计交接包，包含 P2.0—P2.4 范围、契约增量、选型、验收、协作规则和模板。未落地能力必须标记为 `partial`、`stub` 或 `missing`。
- 根目录 `tasks/`：第一阶段历史任务书。第二阶段任务入口在 `Phase_2/tasks/`。

目录名大小写是契约的一部分。代码、PR 和任务说明统一使用 `docs/Phase_1/` 与 `docs/Phase_2/`，不得再新增 `docs/phase1/`、`docs/phase2/`，也不得把阶段文档散放回 `docs/` 根目录。

## Phase 1 基线状态

截至 2026-10-06，远端 `main` 候选为 `a37752073a5fc01337d26e937da55b9226487a34`。PR #8、#12、#13、#14 已合并，Vite 安全维护 PR #15 也已合并；Vite 已锁定为 `7.3.7`，本地 `npm audit` 为 0 个漏洞。

该提交上的 139 项后端测试、30 条 fixture/4 项毛利基线检查、契约生成零漂移、前端干净安装、25 项前端测试、生产构建和真实本地 HTTP 冒烟均通过。当前状态仍是 `candidate_pending_manual`，不是正式 `frozen`：本环境没有可用浏览器，GitHub 匿名 Actions API 返回 403；可见浏览器、报告下载、关键结论支持性、团队财务签核、在线 CI 和第二位开发者独立复现必须由实际执行者补充证据。

详细结果和未完成项见 `Phase_1/README.md` 与 `../validation/Phase1冻结验收记录.md`。

## Phase 2 分支入口

只有 Phase 1 人工门槛完成、冻结文档合并并得到唯一 `main` 冻结提交后，才从该提交建立一次共享 `develop`。P2 短期任务分支从 `develop` 创建并 PR 回 `develop`；阶段候选从 `develop` 建立 `release/phase2-v0.1`，完整验收后 PR 到 `main`。
