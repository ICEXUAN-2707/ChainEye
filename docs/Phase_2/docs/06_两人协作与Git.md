# 两人协作与Git集成

## 职责
Ice/Codex：统筹架构与接口、企业/行业配置、OCR/解析、数据事务、计算、LLM研究、CI、集成与发布。
同学/Claude：数据入口、企业确认、页解析状态、复核联动、五模块工作台、建议/报告展示及交互验收。
两人共同：金融口径、契约变更、样本签核、关键结论支持性、互审。每人主责修改自己的目录；生成类型由工具维护，不能抢改。不要把所有技术工作都留给Ice：前端主责需独立完成状态、接口封装、页面联调与验收记录。

## 分支
main=稳定版；develop=本阶段集成；feat/*=短期任务；release/phase2-v0.1=冻结验收候选；fix/*=缺陷。若当前仓库已有等价分支，先映射不重复建。
从最新稳定main建立develop；feature从develop创建，完成PR到develop；每块真实联调。所有任务完成从develop建立release，修复PR进release并及时同步develop；完整验收后release PR到main，tag与验收commit一致；main回合develop。尚未完成任务不得混入release。
禁止强推共享分支/覆盖历史/未经验证把feature直接进main。个人feature同步develop可merge，冲突解释并解决后回归。生成文件冲突先修权威模型再生成。

## 工作块
|块|Codex分支|Claude分支|集成入口|
|---|---|---|---|
|核查契约|chore/p2-audit-contract|chore/p2-ui-audit|现状、接口样例与错误对齐|
|企业|feat/p2-company-core|feat/p2-company-ui|上传→确认→新版Dataset|
|OCR|feat/p2-parse-core|feat/p2-parse-review-ui|作业→页警告→候选→复核|
|研究|feat/p2-research-core|feat/p2-research-ui|能力检查→五模块→建议|
|报告|feat/p2-report-core|feat/p2-report-ui|快照→导出→原件/计算|

契约新增先小PR进develop，再双方同步开发。前端可使用标识mock准备页面；验收必须真实接口，不用mock替代后台缺失。
PR写清行为、接口/迁移变更、检查结果、限制、另一人复现步骤。另一人复核至少关键流程；Ice最终负责集成，不替前端开发者跑完所有交互检查。

## CI与发布
沿用现有CI：领域/API测试、基线回归、OpenAPI/Schema/TS生成漂移、前端npm ci/build；新增OCR适配器受控fixture测试，普通PR CI不必下载大型权重或调用付费LLM。真实OCR/模型另执行受控集成检查并保存记录，不能仅凭mock放行。
干净clone安装、迁移前备份与恢复、两机原生/扫描各一流程、未见材料、完整报告与证据回查后发布。不会要求用户每个常规本地步骤确认；外部推送/合并遵循用户授权和仓库规则。
