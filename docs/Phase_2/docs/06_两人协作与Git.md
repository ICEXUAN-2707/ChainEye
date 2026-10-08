# 两人协作与Git集成

## 职责
Ice/Codex：统筹架构与接口、企业/行业配置、OCR/解析、数据事务、计算、LLM研究、CI、集成与发布。
同学/Claude：数据入口、企业确认、页解析状态、复核联动、五模块工作台、建议/报告展示及交互验收。
两人共同：金融口径、契约变更、样本签核、关键结论支持性、互审。每人主责修改自己的目录；生成类型由工具维护，不能抢改。不要把所有技术工作都留给Ice：前端主责需独立完成状态、接口封装、页面联调与验收记录。

## 分支
main=稳定版；短期 chore/refactor/feat=可独立审查任务；release/phase2-v0.1=冻结验收候选；fix/*=缺陷。若当前仓库已有等价分支，先映射不重复建。

本轮从最新稳定 `main@c764218` 创建 `chore/p2-agent-baseline`，先完成不改变行为的现状与交付边界。随后依次进行 Registry、Orchestrator、MCP、原生复现，每个 PR 合并后后一分支才基于最新集成基线建立。共享 `develop` 只在团队确认 Phase 1 正式冻结并决定启用后创建一次；在此之前不伪造 frozen 状态，也不把未合并的前置实现当成后续基线。

所有任务完成后从集成基线建立 release，修复 PR 进 release 并及时同步开发线；完整验收后 release PR 到 main，tag 与验收 commit 一致。尚未完成任务不得混入 release。
禁止强推共享分支/覆盖历史/未经验证把feature直接进main。个人feature同步develop可merge，冲突解释并解决后回归。生成文件冲突先修权威模型再生成。

## 工作块
|块|Codex分支|Claude分支|集成入口|
|---|---|---|---|
|Agent 基线|chore/p2-agent-baseline|chore/p2-ui-audit|现状、交付结构、接口样例与错误对齐|
|Registry|refactor/p2-agent-registries|无前端业务修改|Tool/Prompt/Skill 单一注册源|
|编排|refactor/p2-agent-orchestrator|按已审契约展示 trace|显式 graph/state/node 与旧 Run 回归|
|MCP|feat/p2-mcp-mvp|无前端业务修改|stdio 协议、只读资源/工具、真实 smoke|
|原生复现|feat/p2-native-reproduction|补充前端启动/验收说明|Windows/Ubuntu 命令、日志与 trace 导出|
|企业|feat/p2-company-core|feat/p2-company-ui|上传→确认→新版Dataset|
|OCR|feat/p2-parse-core|feat/p2-parse-review-ui|作业→页警告→候选→复核|
|研究|feat/p2-research-core|feat/p2-research-ui|能力检查→五模块→建议|
|报告|feat/p2-report-core|feat/p2-report-ui|快照→导出→原件/计算|

契约新增先小PR进develop，再双方同步开发。前端可使用标识mock准备页面；验收必须真实接口，不用mock替代后台缺失。
PR写清行为、接口/迁移变更、检查结果、限制、另一人复现步骤。另一人复核至少关键流程；Ice最终负责集成，不替前端开发者跑完所有交互检查。

## CI与发布
沿用现有CI：领域/API测试、基线回归、OpenAPI/Schema/TS生成漂移、前端npm ci/build；新增OCR适配器受控fixture测试，普通PR CI不必下载大型权重或调用付费LLM。真实OCR/模型另执行受控集成检查并保存记录，不能仅凭mock放行。
Agent/MCP 阶段新增 graph/registry、协议、replay、日志脱敏和跨平台 smoke；Ubuntu 与 Windows 都不得依赖付费模型完成 CI。干净clone安装、迁移前备份与恢复、两机原生/扫描各一流程、未见材料、完整报告与证据回查后发布。本阶段不以 Docker 作为复现或发布门槛。不会要求用户每个常规本地步骤确认；外部推送/合并遵循用户授权和仓库规则。
