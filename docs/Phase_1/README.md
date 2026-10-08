# Phase 1 基线冻结记录

状态：`candidate_pending_manual`

核对日期：2026-10-08

## 当前候选

|对象|提交|状态|
|---|---|---|
|远端 `main`|`c7642185458a37719ca210a08b7cd8e18f3e129a`|PR #17 已合并；当前自动化冻结候选|
|PR #8、#12—#14|见 `main` 历史|R5 前端、Claim 支持性修复、界面追溯修复与使用手册均已合并|
|PR #15 Vite 安全维护|`9be25f4fa33f17d9da98566af76a11a58a139e97`|已合并；Vite `7.3.7`，本地审计 0 个漏洞|
|PR #17 诊断与 PDF 修复|`46fbaef012dc99ca570eae563ab1e09e3a87df48`|已合并；诊断比较、数据集身份、CJK 字体与回归测试进入 `main`|
|正式冻结提交|`pending`|须在人工门槛完成且本冻结文档合并后填写唯一 `main` SHA|

候选提交不是正式冻结提交。不得从未合并的文档分支、临时合并提交或仍有人工阻塞的候选创建 Phase 2 功能分支。

## 最新 `main` 自动化结果

执行环境：Windows NT `10.0.26200.0`、Python `3.12.10`、Node.js `24.13.0`、npm `11.6.2`。Python 命令使用仓库 `.venv` 与 `backend/requirements.lock`。

- `.venv\Scripts\python.exe -m unittest discover -s tests -v`：141 项通过，220.321 秒。
- `.venv\Scripts\python.exe tools/verify_baseline.py`：30 条 fixture、4 项毛利校验、文件哈希与契约引用通过；该结果不代表未见材料上的自动提取准确率。
- `tools/export_contracts.py`、`tools/generate_ts.py`、`git diff --exit-code -- contracts frontend/src/api/generated.ts`：OpenAPI/Schema `0.4.0`，生成物零漂移。
- `npm.cmd ci --prefix frontend`：干净安装成功；`npm.cmd audit --prefix frontend --json` 为 0 个漏洞。
- `npm.cmd run build --prefix frontend`：28 项前端测试、TypeScript 检查和 Vite `7.3.7` 生产构建通过，44 个模块完成转换。
- `.venv\Scripts\python.exe tools/smoke_local.py`：真实本地 HTTP、前端 HTML、CORS、上传、15 条候选提取、revision/version 更正、重复来源、9 条情景计算、Run、事件游标及未配置密钥/报告未就绪边界通过。
- 工作树在生成检查后保持干净，没有遗留本项启动的前端 Node 进程。

## 未执行或待实际人员确认

- 本环境的 Computer Use 返回 `apps=[]`、`browsers=[]`；普通浏览器和内置浏览器均返回 unavailable。因此没有在本次候选上执行桌面/390px、报告失败重试、旧 Run 隔离和 Markdown/PDF 下载的可见浏览器验收。
- PR #17 合并后的 `main` GitHub Actions verify 已成功；对应 run `37623632932`、job `112799791074`。
- 第二位开发者独立复现、PR 互审结论、30 条关键财务标注签核、关键 Claim 证据支持性和供应商账单核对只能由实际执行者确认，本记录不代签。
- 团队已决定 Phase 2 不做 Docker/Compose；这不是 Phase 1 阻塞。跨平台原生复现、访问保护、备份恢复、发布 tag 和视频仍属于后续交付。

## 正式冻结顺序

1. 实际人员补齐可见浏览器、报告下载、关键结论支持性、财务签核、第二位开发者独立复现、PR 互审和在线 CI 记录。
2. 将本文件和 `validation/Phase1冻结验收记录.md` 的状态改为 `frozen`，保留失败与限制，不删除历史待办。
3. 合并冻结文档 PR，在最新 `main` 再跑仓库规定的全部检查，并把实际合并后的唯一 SHA 写入冻结记录。
4. 仅从该唯一冻结 SHA 创建并推送一次共享 `develop`；P2.1—P2.4 功能分支不得提前建立。
