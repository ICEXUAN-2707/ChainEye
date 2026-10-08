# 给Codex CLI的启动指令

你接手链眼第二阶段。用户要求把现有 demo 完善为证据约束的全链路 Agent，随后支持多电池企业、扫描 PDF 与新能源深度研究。两名开发者：你负责架构/核心后端/集成，Claude负责前端。
先读取仓库AGENTS/README、`docs/Phase_2/`全部文档以及当前代码/迁移/契约/测试。不要把旧R1测试结果当当前结果，不重建或覆盖现有仓库，不处理无关未提交改动。

冻结顺序：Agent 基线→Tool/Prompt/Skill Registry→显式 Orchestrator→stdio MCP MVP→Windows/Ubuntu 原生复现→第二企业→OCR→五模块研究。团队已决定不做 Docker/Compose。MCP 首版只读，不提供任意 shell/SQL/文件/网络能力。

第一轮执行：
1. 记录当前分支、commit、未提交状态和远程；核查现有上传、复核、场景、Run、模型与报告，按implemented/partial/stub/missing逐项举证。
2. 先完成 current-state、contract-delta、比赛交付映射与双系统矩阵；不另手写一份 OpenAPI 作为权威。
3. 迁移现有六个 Tool 到单一 Registry；Prompt 文件化并记录 SHA256；Skill 必须由运行时加载，不以孤立文档冒充。
4. 把现有 Run 主链迁移为可导出的 typed graph，保持预算、失败、恢复、回放和报告语义；不得另建平行 Run。
5. 在统一 Registry 上实现 stdio MCP 的只读 resources/tools、协议测试和真实 smoke，再补结构化脱敏日志与原生复现命令。
6. Agent/MCP/复现关口通过后，才检索并实测 OCR 候选、获取第二企业官方财报和实施 P2.1/P2.2。按块提交可审查 PR，不一次性重写全系统。

live 需要真实 DeepSeek 密钥；replay 必须来自已保存的真实 Run，不能用 mock 冒充。若未选择出可用 OCR，保持 needs_review 降级并保存失败结果。涉及改变金融含义/首版范围时列具体方案由团队决策。
后续按P2.3五模块研究、条件性建议、P2.4完整集成推进；所有数字来自程序与真实证据。保存真实运行结果和未完成项，不伪造通过。
每次报告：新增行为、关键文件、契约/迁移变化、检查命令与结果、限制、Claude联调步骤及下一块任务。
