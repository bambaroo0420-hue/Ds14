const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
const start = source.indexOf('function batchStatus(');
const end = source.indexOf('async function loadPreprocessingPreview', start);
assert.ok(start > 0 && end > start);
const elements = {};
const state = {images:{a:{name:'A'}, b:{name:'B'}, c:{name:'C'}},
  preprocessing:{a:{scale_requested:true}, b:{regions_applied:true, reviewed:true}, c:{scale_status:'failed'}},
  scale:{a:{nm_per_px:1, confirmed:true}}, legacy_templates_enabled:false};
const context = vm.createContext({state, current:'a', escapeHtml:x=>x,
  $:id=>elements[id]||(elements[id]={})});
vm.runInContext(source.slice(start,end),context);
assert.equal(context.batchStatus(undefined),'미적용');
assert.equal(context.batchStatus({}),'제외 미적용');
assert.equal(context.batchStatus(state.preprocessing.a),'스케일 설정 · 제외 미적용');
assert.equal(context.batchStatus(state.preprocessing.b),'제외 검수 완료');
assert.equal(context.batchStatus(state.preprocessing.c),'검출·처리 실패');
context.renderBatchResults();
assert.equal(elements.batchSummary.textContent,'전체 3 · 제외 적용 1 · 제외 검수 완료 1 · 스케일 확정 1 · 실패 1');
assert.match(elements.batchResults.innerHTML,/스케일 설정 · 제외 미적용/);
console.log('PASS batch scale/exclusion status separation');
