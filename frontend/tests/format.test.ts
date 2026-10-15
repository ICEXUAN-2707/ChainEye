import test from 'node:test';
import assert from 'node:assert/strict';
import {datasetLabel,fmtRaw} from '../src/lib/format.ts';

test('CNY_yuan raw values display as exact yuan strings without scaling',()=>{
  assert.equal(fmtRaw('900719925474099312345678.9','CNY_yuan'),'900719925474099312345678.9 元');
});

test('existing thousand and percent raw display remains unchanged',()=>{
  assert.equal(fmtRaw('316506370','CNY_thousand'),'316506370 千元');
  assert.equal(fmtRaw('23.85','percent'),'23.85%');
});

test('EVE datasets use the frozen Chinese company label',()=>{
  assert.equal(datasetLabel({id:'eve-2025',name:'未见样本',company:'EVE',year:2025}),'未见样本 · 亿纬锂能 2025 年报 · eve-2025');
});
