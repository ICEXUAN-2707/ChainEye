# Phase 1 基线冻结记录

状态：`pending`

核对日期：2026-10-06

## 当前候选

|对象|提交|状态|
|---|---|---|
|远端 `main`|`5c80ae1`|已合并PR#9，包含R5后端；尚未包含R5前端|
|PR#9 R5后端|`88b5012`|已于`5c80ae1`合并到`main`|
|PR#8 R5前端|`ede1c1f`|已同步`origin/main`并补齐追溯、恢复请求、错误重试与旧响应隔离；待另一开发者复核及合并|

本表只记录候选身份，不代表PR已合并或验收已完成。本地为审查生成的临时合并提交不得作为发布或冻结依据。

## 2026-10-06 本地复核事实

以下结果在PR#8头`ede1c1f`上执行；该分支已包含`origin/main@5c80ae1`：

- `.venv\Scripts\python.exe -m unittest discover -s tests -v`：135项通过，117.577秒。
- `.venv\Scripts\python.exe tools/verify_baseline.py`：30条fixture、4项毛利校验、文件哈希与契约引用通过；不代表自动提取准确率。
- `tools/export_contracts.py`、`tools/generate_ts.py`及生成物`git diff --exit-code`：通过，OpenAPI/Schema/TypeScript无漂移。
- `npm.cmd ci --prefix frontend`：干净安装成功；随后生产构建中的24项前端测试、TypeScript检查和Vite构建通过。
- `.venv\Scripts\python.exe tools/smoke_local.py`：真实本地HTTP、上传提取复核、情景、Run事件游标及无密钥降级通过。
- `npm.cmd audit --prefix frontend --json`：发现1项high级直接开发依赖风险，当前Vite `7.2.2`受影响，可升级到`7.3.7`；尚未修复，不能遗漏到发布计划之外。
- `git ls-remote origin refs/pull/8/head refs/pull/8/merge`：远端PR头为`ede1c1f`且存在合并引用；这只证明GitHub能生成合并结果，不等同于CI、互审或人工验收通过。

GitHub匿名API因共享出口限流，未能读取最新在线审查/检查详情；可见浏览器也不可用。因此在线CI状态、页面交互和审查意见仍须由实际GitHub页面复核。

## 正式冻结门槛

1. 另一名开发者在PR#8复现至少一个“完成Run→报告→Claim引用→Evidence/Calculation/Assumption→导出”纵向流程，核对在线CI和审查意见后合并；自动化或本助手不得代签。
2. 以独立依赖维护PR升级Vite到无已知上述漏洞的锁定版本，重跑`npm ci`、测试、构建和本地访问边界检查；不要把无关依赖改动混入PR#8。
3. 在PR#8合并后的最新`main`重新执行后端全量测试、`tools/verify_baseline.py`、契约重新生成及零漂移检查、前端锁依赖安装与生产构建、真实本地HTTP冒烟。
4. 人工检查可见浏览器中的报告加载/失败重试/旧Run隔离/窄屏展示，以及Markdown/PDF下载；逐项签核关键结论的证据支持性并记录真实失败。
5. 将本文件状态改为`frozen`，只填写一个实际`main`提交号、环境与冻结日期；再从该提交创建一次Phase 2共享`develop`。

在上述条件满足前，不创建Phase 2功能分支，不修改现有生产契约和迁移，不提前开发P2.1—P2.4。
