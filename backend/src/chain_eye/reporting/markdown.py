"""Markdown export for the frozen Report DTO."""
import json
from urllib.parse import quote,urlsplit

from chain_eye.reporting.common import formula_expression


def _escape(value):
    text=str(value).replace('\\','\\\\').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    for char in ('`','*','_','[',']'):
        text=text.replace(char,f'\\{char}')
    return text


def _evidence_link(evidence_id):
    return f'[{_escape(evidence_id)}](/api/v1/evidence/{quote(evidence_id,safe="")})'


def _calculation_link(calculation_id):
    return f'[{_escape(calculation_id)}](/api/v1/calculations/{quote(calculation_id,safe="")})'


def _external_link(url):
    if not url or urlsplit(url).scheme.casefold() not in ('http','https'):return '原文链接不可用'
    return f'[打开原文]({quote(url,safe=":/?#[]@!$&\'*+,;=%")})'


def render_markdown(report):
    lines=[
        f'# {_escape(report.title)}','',
        f'- Run：`{_escape(report.run_id)}`',
        f'- 数据快照：`{_escape(report.dataset_id)}@{report.dataset_version}`',
        f'- 模式：`{report.mode}`',f'- 生成时间：`{_escape(report.generated_at)}`','',
        '## 结论','',
    ]
    if not report.claims:lines.extend(['当前没有通过报告门槛的 Claim；请查看限制说明。',''])
    for index,claim in enumerate(report.claims,1):
        lines.extend([
            f'### {index}. {_escape(claim.kind)} · {_escape(claim.review_status)}','',
            _escape(claim.text),'',
            f'- 支持证据：{", ".join(_evidence_link(item) for item in claim.evidence_ids) or "无"}',
            f'- 反证：{", ".join(_evidence_link(item) for item in claim.counter_evidence_ids) or "无"}',
            f'- 计算：{", ".join(_calculation_link(item) for item in claim.calculation_ids) or "无"}',
            f'- 假设：{", ".join(f"`{_escape(item)}`" for item in claim.assumption_ids) or "无"}',
            f'- 限制：{_escape("；".join(claim.limitations)) if claim.limitations else "无"}','',
        ])

    lines.extend(['## 事实快照',''])
    for fact in report.facts:
        value=fact.value if fact.value is not None else f'缺失（{fact.missing_reason}）'
        lines.extend([
            f'### `{_escape(fact.id)}@{fact.revision}`','',
            f'- 指标/业务/期间：`{fact.metric}` / `{fact.segment}` / `{fact.period_end}`',
            f'- 规范值：`{_escape(value)}` `{fact.unit}`；状态：`{fact.status}`',
            f'- 原值：`{_escape(fact.raw_value) if fact.raw_value is not None else "null"}` `{fact.raw_unit}`',
            f'- 证据：{", ".join(_evidence_link(item) for item in fact.evidence_ids) or "无"}','',
        ])

    lines.extend(['## 计算与公式',''])
    for calculation in report.calculations:
        inputs=', '.join(f'`{_escape(item)}@{calculation.input_revisions[item]}`' for item in calculation.input_fact_ids) or '无'
        value=f'`{_escape(calculation.value)}` `{calculation.unit}`' if calculation.value is not None else f'不可计算：{_escape(calculation.reason)}'
        lines.extend([
            f'### `{_escape(calculation.id)}`','',
            f'- 公式：`{_escape(calculation.formula_id)}@{_escape(calculation.formula_version)}` — `{_escape(formula_expression(calculation.formula_id))}`',
            f'- 输入事实：{inputs}',f'- 结果：{value}',
            f'- 假设快照：`{_escape(json.dumps(calculation.assumption_snapshot,ensure_ascii=False,sort_keys=True,separators=(",",":")))}`','',
        ])

    lines.extend(['## 条件情景与假设',''])
    if not report.scenarios:lines.extend(['本 Run 未执行条件情景。',''])
    for scenario in report.scenarios:
        lines.extend([
            f'### 情景 `{_escape(scenario.scenario_id)}`','',
            f'- 模型：`{_escape(scenario.model_version)}`；假设：`{_escape(scenario.assumption_id)}`',
            f'- 基线：`{_escape(json.dumps(scenario.baseline.model_dump(mode="json"),ensure_ascii=False,sort_keys=True,separators=(",",":")))}`',
            f'- 输出：`{_escape(json.dumps(scenario.outputs.model_dump(mode="json"),ensure_ascii=False,sort_keys=True,separators=(",",":")))}`',
            f'- 计算：{", ".join(_calculation_link(item) for item in scenario.calculation_ids)}','',
        ])
    for assumption in report.assumptions:
        lines.extend([
            f'### 假设 `{_escape(assumption.id)}`','',
            f'- 参数：`{_escape(json.dumps(assumption.values.model_dump(mode="json"),ensure_ascii=False,sort_keys=True,separators=(",",":")))}`','',
        ])

    lines.extend(['## 证据',''])
    for evidence in report.evidence:
        if evidence.locator_kind=='pdf':
            locator=f'PDF 第 {evidence.pdf_page} 页'
            original=f'[打开原件](/api/v1/sources/{quote(evidence.source_id,safe="")}/content#page={evidence.pdf_page})'
        else:
            locator=f'HTML `{_escape(evidence.selector or "")}`';original=_external_link(evidence.url)
        lines.extend([
            f'### `{_escape(evidence.id)}`','',
            f'- 来源：`{_escape(evidence.source_id)}`；定位：{locator}；{original}',
            f'- SHA256：`{evidence.sha256}`','- 摘录：','',
        ])
        lines.extend(f'> {_escape(line)}' for line in evidence.excerpt.splitlines() or [''])
        lines.append('')

    lines.extend(['## 限制与风险边界',''])
    lines.extend(f'- {_escape(item)}' for item in report.limitations)
    lines.append('')
    return '\n'.join(lines)
