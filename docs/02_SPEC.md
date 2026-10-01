# 链眼工程规格 v0.2

## 架构与职责
采用单体后端和独立前端，避免两人维护多服务。后端建议FastAPI、Pydantic、SQLite、PyMuPDF、Decimal；前端React与TypeScript。HTTP客户端用于DeepSeek适配，不把供应商响应格式传播到领域模块。R1依赖已锁定于backend/requirements.lock及frontend/package-lock.json；requirements-validation.txt仅保留R0历史用途。
不用动态执行模型生成Python、不开放任意Shell、不依赖Neo4j/Milvus。检索先做SQLite全文索引加页级关键词，语义检索作为后续可替换适配器。

目标代码结构：
```
backend/src/chain_eye/
  api/                 路由、HTTP DTO、错误映射
  application/         用例、事务、任务执行与快照
  domain/              事实、假设、计算、Claim、纯计算规则
  ports/               Repository、LLM、Parser、Retriever接口
  adapters/            sqlite、pymupdf、deepseek、全文检索
  agents/              plan、extract、research、synthesis配置
  tools/               工具注册与输入输出校验
  reporting/           结构化报告、Markdown、PDF渲染
frontend/src/
  api/                 从契约生成的类型与请求封装
  pages/ components/   交互与展示
  state/               Run轮询、过期结果与错误状态
contracts/ tests/ data/ docs/
```
R1已迁入backend/src，生成类型位于frontend/src/api/generated.ts。上图为最终目标，尚未实现的目录不代表现有能力。
依赖方向：api→application→domain/ports；adapters实现ports，通过组合入口注入。领域模块不得导入HTTP、数据库、LLM或前端。前端不计算权威金融结果，只格式化后端结果。

## 冻结领域契约
见contracts/*.schema.json及domain/contracts.py。金额CNY十进制字符串，不用JSON float；比率ratio，百分点pp。输入端日期须校验ISO真实日期，期间起止合法。value=null必须有missing_reason，不能用0或空字符串代表缺失。
Source保存id/url/文件哈希/发布日期/取得时间/媒体类型。Evidence保存source_id、PDF从1开始页码、印刷页码和可选bbox或HTML定位、短摘录、哈希。没有精确bbox时仅定位页，不能画一个虚假高亮框。
Fact区分group/power_battery/energy_storage、annual_flow/point_in_time，保存原值及原单位、规范值、revision、证据、状态和重述状态。
Assumption包含s/x/k、basis和用户确认；必须标为假设。Claim分类fact/calculation/inference/opinion/hypothesis，并有证据、计算、参数引用、反证和限制。
Calculation保存公式版本、所有输入事实revision、参数快照、结果及不可计算原因。
Dataset与Run必须引用具体版本，不跟随最新事实静默改变。

## 数据库与不可变快照
R1实际表见backend/migrations/001_initial.sql：datasets、dataset_snapshots、sources、dataset_sources、facts（id/revision联合键）、dataset_facts、fact_corrections、evidence、runs、run_events、calculations、scenarios、reports、idempotency；除样本与数据包读写外，后续业务表尚未接入服务。UUID或等价全局唯一ID，不用文件路径当外部ID。
文件按sha256存放，元数据指向内容；原始文件不覆盖。更正产生新revision和dataset版本，旧结果保留并标stale。新Run绑定新版本，旧Run始终使用旧快照。事务保证revision比较和更新原子性。SQLite开启WAL，单worker领取作业；不要跨多个API进程各建独立内存队列。

## 模型公式与范围
v1固定销量、业务结构和其他投入，参数s∈[0,1]、x∈[-0.5,0.5]、k∈[0,1]。
ΔC=C0*s*x；C1=C0+ΔC；R1=R0+k*ΔC；GP1=R1-C1；GM1=GP1/R1。
ΔGP=(k-1)*ΔC；ΔGM_pp=100*(GM1-GM0)。使用Decimal至少28位有效精度。仅展示时四舍五入；不允许从已舍入结果继续计算。
合法基线收入>0、成本>=0、同公司同业务同年度同币种同报表范围、状态verified；本功能只接动力或储能业务。结果收入<=0或成本<0返回INVALID_SCENARIO，不裁剪参数掩盖问题。
用户确认假设后可使用演示网格，27个确定性计算。不能把技术范围解释成经验区间或置信区间。
首版不计算公司实际净利润预测、不使用总电池销量估算分业务单价。

## 编排
Run状态queued→running→waiting_review/completed/partial/failed/cancelled。
节点plan→extract→validate→finance→research→scenario→verify→report。scenario节点只在任务包括情景且参数齐备时执行；缺参数停在waiting_review。
节点状态与结果落盘；任务运行即使前端关闭也能继续。单worker通过SQLite作业状态领取，启动时标记被中断的节点并仅重试安全的幂等操作。
LLM负责受控任务计划、候选字段语义定位、证据筛选和叙述。程序负责解析、所有计算、引用存在性、口径验证和预算控制。
引用存在不等于支持结论：存在性由程序检查，支持性通过短证据对照和人工抽查评估。引文不支持的结论降为insufficient或删除。
文档内容是数据，不能覆盖系统指令。模型工具白名单：search_documents、get_evidence、get_facts、compute_financials、compute_scenario、validate_claims。禁止任意代码执行、任意URL抓取；网络采集在独立准备阶段。
工具调用结构{call_id,run_id,tool_name,tool_version,input,output,status,error,started_at,ended_at}，输入输出大小限额并记录哈希。只保存可公开的计划与简要理由，不保存或要求模型隐藏思维链。
DeepSeek实际调用、模型ID、输出格式能力、费用和超时需R4验证，当前未调用API。模型配置和Prompt文本版本保存到Run，API key不得入库/日志/前端。

## API与错误
精确路由见OpenAPI 3.1；请求/响应体schema互相引用。状态读写是后端权威，前端轮询GET /runs/{id}与事件游标。
POST /runs与POST /scenarios支持Idempotency-Key，dataset_id+键范围内相同body复用结果，不同body返回409。JSON规范化后哈希；保留24小时以上。
事实更正expected_revision，旧版本返回409 REVISION_CONFLICT。外部工具失败返回结构化错误，不以空报告表示成功。
错误码：INVALID_INPUT/INVALID_BASELINE/INVALID_SCENARIO/SCOPE_MISMATCH/FACT_NOT_VERIFIED/REVISION_CONFLICT/PRICE_SERIES_INCOMPLETE/LLM_UNAVAILABLE/BUDGET_EXCEEDED/NOT_FOUND。
HTTP 422输入，409冲突或需复核，404不存在，429限额，503供应商暂不可用，500意外异常；统一error包装，含request_id和retryable，不暴露密钥与内部路径。

## 价格模块
series_id锁定供应商、商品规格、spot/index/futures、币种、单位、税口径及区域。price_date是交易/报价日期，不是抓取日期。单个日期的指数和现货均价不能合并。
首版仅PriceObservation样本展示，不进入自动冲击计算。历史模式开放条件：同series、一个完整选定窗口（先30个报价日）、有效预期日历、覆盖率>=95%、重复和缺失清单、原始来源可核验；均价请求对任何缺失日应拒绝或明确指定只用观测日口径，不默默补齐。
期货必须用固定合约或预先声明换月规则，不能自动拼接“主力”造成伪价格跳变。

## 部署与安全边界
本地开发单用户；公网版本有团队登录，dataset/run/report按owner检查访问。文件访问通过ID映射、路径约束，防路径穿越；PDF上限30MiB、最多500页、最多5份/数据包，恶意/加密PDF返回错误。公网不允许用户上传后被其他用户读取。
Docker Compose构建API和Web，SQLite及文件目录持久化，健康检查、启动迁移、依赖锁定；不将密钥打包。提供数据备份恢复和新电脑操作说明。
现场在线实时模式需要API网络；回放模式不调用模型并显著标记。回放复现保存数字和引用，不承诺实时LLM逐字复现。

## Python内部接口
- Parser.parse(source_id, bytes) -> DocumentPages：每页{page_no,text,blocks,table_candidates,parse_warnings}，页号从1开始，块bbox坐标为原PDF点。
- FactRepository.get(dataset_id, dataset_version, fact_id, revision) -> Fact：版本或归属错误拒绝，不返回最新版本替代。
- Retriever.search(dataset_id, dataset_version, query, filters, top_k<=8) -> Evidence[]：仅数据包范围，返回真实Evidence ID，不由模型生成来源。
- FinancialService.compute(fact_snapshot, requested_metric_ids) -> Calculation[]：输入不足返回not_computable及原因，不抛弃整个报告。
- ScenarioService.execute(ScenarioRequest, idempotency_key) -> ScenarioResult：查库验证revision和口径，调用纯内核，落库Calculation后返回。
- LLMPort.generate(task_name, prompt_version, messages, response_schema, budget) -> LLMResponse：结构化对象、模型ID、token用量、耗时、request_id；失败为TypedProviderError。
- RunRepository.append_event(run_id, event) -> seq：事务分配单调seq；不同Run独立序列。预算和超时分别记录。
- ReportService.build(run_snapshot, claims, calculations) -> Report：只接受已校验引用；文件导出由reporting适配器实现。

## 工具输入输出契约
|工具|输入|输出|失败处理|
|---|---|---|---|
|search_documents|dataset_id/version,query,filters,top_k|Evidence列表|空列表表示无结果；不伪造来源|
|get_evidence|evidence_ids|Evidence列表|不存在返回NOT_FOUND|
|get_facts|dataset_id/version,metric_ids,segment,period|Fact列表|missing保留，不以0替换|
|compute_financials|fact_ids/revisions,metric_ids|Calculation列表|not_computable+原因|
|compute_scenario|ScenarioRequest|ScenarioResult|口径/状态/参数错误TypedError|
|validate_claims|Claim列表,允许引用集合|每条claim的存在性结果、支持性待复核状态|拒绝不合法引用，语义支持检查另进行|
模型不能写入verified状态。复核权属于人工操作或事先批准的确定性规则；初赛基线以人工复核为准。

RunCreate约束：mode=replay必须给replay_run_id；源Run属于同owner且快照一致。mode=live不得设置replay_run_id。replay运行不调用模型。动态约束由application检查并列入契约测试。
所有来源、证据、事实引用均检查dataset/version/owner，ID存在性不足以证明访问合法。

## R1实现状态与契约权威
R1仅本机单用户。所有目标功能的实现状态以validation/R1验收记录.md为准。上传返回SourceAttachment（新版Dataset及Source），事实查询version必填。Source身份独立于数据包。HTTP DTO位于api/dto.py，领域数据位于domain；生成规范与实际路由一致。ports/services.py是后续服务协议骨架，不代表服务已实现。
