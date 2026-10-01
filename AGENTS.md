# 链眼协作约束

本仓库由两名开发者共同维护。Codex 负责后端与最终集成，Claude 负责前端。所有结论必须以可复现命令和真实输出为依据；失败、未执行、人工待复核与实机待验证不得写成成功。

## 目录职责

- Codex：`backend/**`、`backend/migrations/**`、后端相关 `tests/**`、后端工具与最终集成。
- Claude：`frontend/**` 的页面、组件、样式、状态与交互。
- 共享：`docs/**`、`validation/**`、`.github/**`、`README.md` 和契约评审。
- `contracts/**` 与 `frontend/src/api/generated.ts` 只允许由 `tools/export_contracts.py`、`tools/generate_ts.py` 生成；禁止手改生成物。
- 不修改另一位开发者职责内的组件或业务实现。跨边界需求先在 PR 中说明接口和影响，由对应负责人修改。

## 契约、金额与版本

- 契约单一来源是 `backend/src/chain_eye/api/app.py` 的路由、`api/dto.py` 的 HTTP DTO 与 `domain/**` 的领域模型。
- 契约变更必须说明原因，并同步模型、OpenAPI、JSON Schema、生成 TypeScript、接口文档与测试；不得另建并行 DTO。
- API 金额是人民币元的十进制字符串，不得使用 JSON 浮点数；原文千元值保留。`ratio` 展示时乘 100，`pp` 不再乘 100。
- Dataset、Run 与计算必须绑定显式版本；来源或事实变化生成新 Dataset 版本。事实更正生成新 revision，旧快照不得被静默覆盖。
- 缺失值是 `null + missing_reason`，不能用 0 或空串替代；模型与自动提取无权写入 `verified`。

## 必跑检查

PowerShell：

```powershell
$env:PYTHONPATH="backend/src"
python -m unittest discover -s tests -v
python tools/verify_baseline.py
python tools/export_contracts.py
python tools/generate_ts.py
git diff --exit-code -- contracts frontend/src/api/generated.ts
npm ci --prefix frontend
npm run build --prefix frontend
python tools/smoke_local.py
```

Linux/macOS 将 `PYTHONPATH=backend/src` 放在 Python 命令前。依赖按 `backend/requirements.lock` 与 `frontend/package-lock.json` 安装。CI 不配置 DeepSeek 密钥，不调用付费模型。

## 分支、提交与 PR

- `main` 始终保持可构建；每项任务从最新 `main` 建立短期分支，如 `feat/r2-upload-backend`。
- 禁止把未评审功能直接提交到 `main`。PR 必须由另一名开发者互审，并至少复现一个关键纵向流程。
- PR 描述必须列出新增行为、契约变化、检查命令和真实结果、限制、人工待办及前后端联调方法。
- 涉及生成契约的 PR 必须包含生成物漂移检查；无契约变化时，生成命令应保持工作树干净。
- 不提交 `.env`、密钥、`.runtime/`、虚拟环境、`node_modules/`、`frontend/dist/` 或临时文件。
- 占位功能继续返回明确的 501；禁止伪造成功响应、截图、测试输出、提取准确率、人工签核或模型调用结果。

团队财务签核、第二位开发者独立复现和双方互审只能由实际执行者确认，自动化或单个助手不得代签。
