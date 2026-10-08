# 第二阶段工程Spec

## 先适配现有工程
先查当前README/AGENTS/迁移/路由/DTO/依赖锁/测试/分支。旧参考栈为FastAPI/Pydantic/SQLite/PyMuPDF/Decimal+React/TypeScript；若仓库已合理改变，记录映射而非重写。
目标仍是单体后端+独立前端+单作业worker。暂不引入必须维护的新数据库/多服务平台。解析/OCR为可替换适配器，文档作业可异步执行并持久化；现有worker可复用。

## Agent Kernel

现有 `RunExecutionService` 是唯一运行系统。改造时把隐式 plan、extract、validate、finance、research、scenario、verify、report 迁移为 typed graph、state 和 node spec，不能另建第二套 Run 或复制业务服务。每个节点声明输入/输出、允许 Skill/Tool、预算、重试、失败、恢复和事件字段；图可导出为稳定 JSON 供评审复现。

六个现有 Tool 迁入单一 ToolRegistry，保留快照作用域、90 秒预算、输入/输出 SHA256 与失败语义。Prompt 从内联常量迁为版本化文件并记录内容 SHA256。Skill 是运行时加载的受约束任务包，至少包含 ID、版本、允许 Tool、Prompt 引用、输入和输出约束；只有说明文档而未被运行时引用不算实现。

Agent/模型不得写入 `verified`、绕过 Dataset version、执行权威金额计算、伪造引用或把缺失值改成 0/空串。财务与情景继续由确定性领域服务计算，Claim 继续经过引用与数字支持检查。

## MCP MVP

MCP 使用独立 stdio 入口，共用 ToolRegistry 和 Repository，不复制 Tool handler。首版提供 Dataset version、Evidence、Run trace、Report、Skill metadata 资源，以及 `get_facts`、`get_evidence`、`search_documents`、`get_run_trace`、`get_report` 只读工具和 Prompt metadata。禁止 HTTP/SSE、公网托管、任意 shell/SQL/文件路径/网络访问、密钥读写和人工 `verified` 写入。

协议测试必须覆盖 initialize、list、合法调用、非法参数、跨快照拒绝、未知版本、敏感信息不外泄与正常退出。`compute_financials`、`compute_scenario`、`validate_claims` 暂不作为 MCP 外部工具，直到上下文、幂等与写入边界另行审查。

## 职责与依赖
api负责HTTP/错误；application负责确认、作业、复核、版本事务和研究；domain负责事实/计算/Claim/金融约束；ports声明Parser/OCR/LLM/Retriever/Repository；adapters连接解析器与供应商。领域不导入OCR/HTTP/LLM。前端只格式化，金额不经parseFloat回写。
配置层采用company_profile+industry_profile+model_applicability。公司适配定义名称别名/业务映射，不含硬编码答案、页码或真实参数。

## PDF管线
1. 上传复用现有限制30MiB/500页/每数据包5份。流式大小限制、实际PDF校验、加密失败、哈希去重。
2. 原件不可覆盖；source按内容身份，关联上下文属于dataset。
3. 页级统计文字量、可打印比例、表格/图片特征，得到native/ocr/hybrid/failed。阈值配置化并在POC记录，不能用单个字符数对所有页做最终判断。
4. 文本可靠页原生解析；扫描/异常页渲染送OCR；混合页只补必要区域，合并时避免双计。
5. 输出统一PageArtifact，保留页号、文字、真实bbox、表格cells、单位/表头/脚注和warnings；跨页表只在表头/列结构可验证时合并，并保留每cell来源。
6. 候选提取识别行名+列年+单位+范围，而非检索数值是否存在。低质量/冲突输出needs_review。
7. 人工复核事务保存Fact revision、Dataset version和更正理由。OCR置信度不等于财务事实正确概率。

原PDF坐标与渲染像素通过显式仿射矩阵转换，记录rotation/cropbox/尺寸；bbox格式为[x0,y0,x1,y1]且坐标空间声明pdf_points_top_left。不能定位时bbox=null、页级证据，禁止假高亮。前端据映射缩放，不猜坐标。

## 异步作业
queued/running/completed/partial/failed/cancelled。已处理页数不等于事实数量；成功处理空白页不是提取到事实。页失败累积为partial；所有页失败为failed。作业完成并不自动verified。
job绑定source hash/dataset base_version/解析配置hash；中途数据包改版时解析候选仍绑定原件，发布候选到快照须检查冲突，不覆盖新数据。重复同键同body复用；同键异body409。
暂停/超时/取消保留页结果；重试按source hash+page+engine/model/config键复用安全结果。文件哈希改变使派生证据失效。

## 双通道研究
结构化Fact查询用于数字；文本/表格/附注检索用于解释。检索必须限定company/dataset/version/source集合，保留章节和页级元数据。优先复用SQLite FTS；若评测证明需向量/重排，再以可替换接口引入，不能默认堆框架。
模型：任务规划→工具读取事实/证据→确定性计算→组织论点→引用与数字校验→建议→报告。各步骤复用现有Run，不另造一套平行运行系统。只记录任务计划与简要依据，不请求隐藏思维链。
LLM输出使用结构化Schema；数字只能引用Fact/Calculation，生成文本中数字与引用需校验。允许引用存在不代表语义支持，关键Claim人工核查；无支持则insufficient。
供应商响应和OCR模型属于适配器；不能假设所选DeepSeek端点接收图片。OCR与文本LLM分开；VLM/API解析若选用须实测能力、费用与数据传输范围。

## 金融规则
保留Decimal及单位、币种、年度、余额/流量、集团/归母/业务、重述口径约束。输入不齐Calculation为not_computable+reason。收入同比需可比两期及非零分母。
M5保持ΔC=C0*s*x；C1=C0+ΔC；R1=R0+k*ΔC；GP1=R1-C1；GM1=GP1/R1。s[0,1]/x[-.5,.5]/k[0,1]只是工程范围。情景结果不可直接当净利润。
建议不得预填公司“真实”合同传导比例；产能、利用率、单位售价必须有匹配分子分母，不能拿总销量替分业务销量。

## 运行约束
先用单并发OCR与研究作业测资源，页面/API保持可用。预算沿用当前配置，若缺失参考上阶段10分钟/12次模型调用/单工具90秒为候选，并按实测分离解析和研究超时；不是已验证SLA。超时partial/failed、可恢复，不伪成功。默认本机；公网需继续完成身份与owner隔离。原件、快照、派生结果和迁移纳入备份。

正式复现环境为 Windows 11 与 Ubuntu，Python 3.12、Node 24、UTF-8、锁文件安装。团队已决定不交付 Docker/Compose。CI 不调用付费模型；live 需要真实密钥，replay 必须源于已保存的真实 Run。结构化 JSONL 日志须脱敏，不记录 API key、Authorization、完整环境变量、无界原文或完整模型请求。
