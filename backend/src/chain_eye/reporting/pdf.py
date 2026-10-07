"""Portable PDF export using PyMuPDF's embedded CJK font."""
import json
import os
import re

import fitz

from chain_eye.reporting.common import formula_expression


def _discover_cjk_font():
    """返回系统里可嵌入的中文字体文件路径；找不到则返回 None 回退到内置字体。"""
    candidates = [
        # Windows
        r'C:\Windows\Fonts\simhei.ttf',
        r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\simsun.ttc',
        r'C:\Windows\Fonts\simkai.ttf',
        # macOS
        '/System/Library/Fonts/PingFang.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        # Linux
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _font_name_and_file():
    """返回 (fontname, fontfile)；fontfile 非空时需在每页 insert_font 注册以真正嵌入。"""
    path = _discover_cjk_font()
    return ('chain-cjk', path) if path else ('china-s', None)

PAGE_WIDTH,PAGE_HEIGHT=fitz.paper_size('a4')
MARGIN=48
BOTTOM=48


def _clean(value):
    safe=''.join(' ' if ord(char)<32 else char for char in str(value))
    return re.sub(r'\s+',' ',safe).strip()


def _lines(report):
    rows=[(report.title,'title'),(f'Run: {report.run_id}','meta'),(f'数据快照: {report.dataset_id}@{report.dataset_version} | 模式: {report.mode} | 生成: {report.generated_at}','meta')]
    rows.append(('结论','heading'))
    if not report.claims:rows.append(('当前没有通过报告门槛的 Claim；请查看限制说明。','body'))
    for claim in report.claims:
        rows.extend([
            (f'[{claim.kind}/{claim.review_status}] {claim.text}','body'),
            (f'证据: {", ".join(claim.evidence_ids) or "无"} | 反证: {", ".join(claim.counter_evidence_ids) or "无"}','small'),
            (f'计算: {", ".join(claim.calculation_ids) or "无"} | 假设: {", ".join(claim.assumption_ids) or "无"}','small'),
        ])
    rows.append(('事实快照','heading'))
    for fact in report.facts:
        value=fact.value if fact.value is not None else f'缺失({fact.missing_reason})'
        rows.append((f'{fact.id}@{fact.revision} | {fact.metric}/{fact.segment}/{fact.period_end} | {value} {fact.unit} | 证据 {", ".join(fact.evidence_ids)}','small'))
    rows.append(('计算与公式','heading'))
    for item in report.calculations:
        inputs=', '.join(f'{fact_id}@{item.input_revisions[fact_id]}' for fact_id in item.input_fact_ids) or '无'
        value=f'{item.value} {item.unit}' if item.value is not None else f'不可计算: {item.reason}'
        rows.append((f'{item.id} | {item.formula_id}@{item.formula_version} | {formula_expression(item.formula_id)} | 输入 {inputs} | 结果 {value}','small'))
    rows.append(('条件情景与假设','heading'))
    if not report.scenarios:rows.append(('本 Run 未执行条件情景。','body'))
    for scenario in report.scenarios:
        rows.extend([
            (f'情景 {scenario.scenario_id} | 模型 {scenario.model_version} | 假设 {scenario.assumption_id}','body'),
            (f'基线 {json.dumps(scenario.baseline.model_dump(mode="json"),ensure_ascii=False,sort_keys=True)}','small'),
            (f'输出 {json.dumps(scenario.outputs.model_dump(mode="json"),ensure_ascii=False,sort_keys=True)}','small'),
            (f'计算 {", ".join(scenario.calculation_ids)}','small'),
        ])
    for assumption in report.assumptions:
        rows.append((f'假设 {assumption.id}: {json.dumps(assumption.values.model_dump(mode="json"),ensure_ascii=False,sort_keys=True)}','small'))
    rows.append(('证据','heading'))
    for evidence in report.evidence:
        locator=f'PDF第{evidence.pdf_page}页' if evidence.locator_kind=='pdf' else f'HTML {evidence.selector or evidence.url}'
        rows.extend([
            (f'{evidence.id} | 来源 {evidence.source_id} | {locator} | SHA256 {evidence.sha256}','small'),
            (f'摘录: {evidence.excerpt}','small'),
        ])
    rows.append(('限制与风险边界','heading'))
    rows.extend((f'- {item}','body') for item in report.limitations)
    return rows


def _wrap(text,font,size,width):
    wrapped=[]
    for paragraph in _clean(text).split('\n'):
        if not paragraph:wrapped.append('');continue
        current=''
        for char in paragraph:
            candidate=current+char
            if current and font.text_length(candidate,fontsize=size)>width:
                wrapped.append(current);current=char
            else:current=candidate
        if current:wrapped.append(current)
    return wrapped


def render_pdf(report):
    document=fitz.open()
    fontname,fontfile=_font_name_and_file()
    font=fitz.Font(fontfile=fontfile) if fontfile else fitz.Font(fontname='china-s')
    styles={
        'title':(17,23,(0.08,0.18,0.28),10),
        'heading':(13,19,(0.07,0.35,0.48),7),
        'body':(10,15,(0.08,0.10,0.13),4),
        'small':(8.5,13,(0.20,0.24,0.28),3),
        'meta':(8.5,13,(0.32,0.36,0.40),3),
    }
    page=None;y=0
    rows=_lines(report)
    for index,(text,style) in enumerate(rows):
        size,line_height,color,after=styles[style]
        wrapped=_wrap(text,font,size,PAGE_WIDTH-2*MARGIN)
        needed=max(1,len(wrapped))*line_height+after
        if style=='heading' and index+1<len(rows):
            next_text,next_style=rows[index+1]
            next_size,next_height,_,next_after=styles[next_style]
            next_lines=_wrap(next_text,font,next_size,PAGE_WIDTH-2*MARGIN)
            needed+=max(1,min(len(next_lines),2))*next_height+next_after
        if page is None or y+needed>PAGE_HEIGHT-BOTTOM:
            page=document.new_page(width=PAGE_WIDTH,height=PAGE_HEIGHT);y=MARGIN
            if fontfile:page.insert_font(fontname=fontname,fontfile=fontfile)
        for line in wrapped:
            page.insert_text((MARGIN,y),line,fontname=fontname,fontsize=size,color=color)
            y+=line_height
        y+=after
    for index,page in enumerate(document,1):
        footer=f'Chain Eye | {report.run_id} | 第 {index}/{len(document)} 页'
        page.insert_text((MARGIN,PAGE_HEIGHT-24),footer,fontname=fontname,fontsize=7,color=(0.45,0.48,0.52))
    document.set_metadata({'title':report.title,'subject':f'Run {report.run_id}','author':'Chain Eye','creator':'Chain Eye R5 deterministic renderer'})
    result=document.tobytes(garbage=4,deflate=True);document.close();return result
