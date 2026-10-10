# 链眼 第二阶段优化资料包 v0.2
更新日期：2026-10-09。两人开发：Ice/Codex负责架构、核心后端与集成；同学/Claude负责前端与交互。

## 本包定位
这是产品、工程和比赛复现交接包，不替换现有仓库。`main/develop@128f2c7` 已包含 R5、Agent 基线和 PR #19 Registry：六个 Tool 使用单一注册源，Prompt 已文件化并绑定 SHA256，三个 Skill 被运行时加载，Run 固化 Tool 实现和模型 provenance。G3 分支 `feat/p2-agent-orchestrator` 已实现显式 graph/state/node、图驱动 live/replay 调度和图级 trace 元数据，等待 PR 互审，尚未合并；MCP、统一 JSONL 日志和跨平台一键复现仍未实现。解析仍只适配宁德时代冻结文本版式，扫描 PDF 无 OCR。原始核查证据见 `records/current-state-2026-10-08.md`，G2/G3 增量分别见仓库 `validation/P2-AgentRegistry验收记录.md` 与 `validation/P2-AgentOrchestrator验收记录.md`。

Phase 1 人工财务签核、第二位开发者独立复现和 PR 互审仍只能由实际执行者确认。本包不把这些待办或未实现的 Agent/MCP 能力写成成功。
“第二阶段”编号P2，是本次功能优化迭代，不等于旧计划中的R2。P2横跨旧R2数据、R3计算、R4研究和R5报告；旧阶段要求继续有效，缺失基础须先补齐。

## 已冻结决定
定位：证据约束的新能源电池产业链全链路研究 Agent；宁德时代主案例，至少一家同类型电池企业迁移验证；企业可解析与专项模型可用分开；按页OCR；证据与程序计算支撑深度分析；条件性建议与研究缺口明确。
支持 Windows 11 与 Ubuntu 原生复现，不做 Docker/Compose。先落地 Agent Kernel、MCP MVP 和复现链，再扩展第二企业与 OCR。MCP 首版只做 stdio、协议测试和真实最小调用。
不承诺整个新能源行业全覆盖，不新增买卖评级、目标价、公司真实净利润预测或无数据支持的历史价格回测。

## 阅读顺序
1. docs/00_决策与阶段地图.md
2. docs/01_PRD.md
3. docs/02_SPEC.md
4. docs/03_契约与数据协议.md
5. docs/04_GitHub尽调与选型.md
6. docs/05_验收与评测.md
7. docs/06_两人协作与Git.md
8. docs/07_剩余任务执行计划.md
9. docs/08_Agent内核与MCP实施计划.md
10. records/current-state-2026-10-08.md、records/contract-delta-2026-10-08.md
11. tasks/Codex_启动指令.md、tasks/Claude_启动指令.md

本目录在仓库中的规范路径固定为 `docs/Phase_2/`，上面的 `docs/`、`tasks/` 与 `templates/` 路径均相对此目录。先使用任务指令核查当前实现、补迁移计划，再逐块实施。不要用本包里的示例覆盖生产数据、金标准或生成OpenAPI。

## 最终交付
完整源代码须与现场版本一致，并包含显式 Agent graph、白名单 Tool、版本化 Prompt、运行时 Skill、stdio MCP、数据处理、结构化脱敏日志、依赖锁和 Windows/Ubuntu 运行说明。产品能力支持至少两家电池企业的上传研究工作台；文本/扫描/混合PDF处理与复核；五模块研究、可用性检查、建议卡片；JSON/Markdown/PDF报告；原件与计算证据链；live/replay 区分、评测集清单、结果及复现说明。
