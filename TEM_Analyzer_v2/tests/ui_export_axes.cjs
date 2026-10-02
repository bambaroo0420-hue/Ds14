// Focused checkbox synchronization and request-contract fixture; GUI separate.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');const ids={};
class Element{
 constructor(){this.value='';this.checked=false;this.children=[]}
 set innerHTML(html){this.html=html;for(const m of html.matchAll(/id="([^"]+)"([^>]*)/g)){const e=ids[m[1]]=new Element();e.value=m[2].match(/value="([^"]*)"/)?.[1]||'';e.checked=/\bchecked\b/.test(m[2])}}
 get innerHTML(){return this.html||''}append(...x){this.children.push(...x)}after(){}closest(){return this}querySelector(){return this}addEventListener(){}removeAttribute(){}showModal(){}close(){}
}
for(const id of ['maskSelectionCount','measure','batch'])ids[id]=new Element();
const document={body:new Element(),createElement:()=>new Element(),getElementById:id=>ids[id]},window={addEventListener(){},dispatchEvent(){}};
const T={state:{images:{a:{name:'a'}},mask_scopes:{}},current:'a',say(){},escape:s=>s};
const ctx=vm.createContext({document,window,Event:class{}});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/modules/scopes.js'),'utf8').replace('export function','function')+'\nthis.mount=mountScopes;',ctx);
ctx.mount(T,{ids:()=>[]});assert(T.exportOptions().export_all_axes);assert(ids.exportAxes_measure.checked&&ids.exportAxes_batch.checked);
ids.exportAxes_batch.checked=false;ids.exportAxes_batch.onchange();assert(!ids.exportAxes_measure.checked);assert(!T.exportOptions().export_all_axes);
ids.exportAxes_measure.checked=true;ids.exportAxes_measure.onchange();assert(ids.exportAxes_batch.checked);assert(T.exportOptions().export_all_axes);
ids.analysisScope.value='selection';ids.maskScopeId.value='target';ids.exportPartialGT.checked=true;
assert.equal(T.exportOptions().scope_id,'target');assert(T.exportOptions().include_gt);assert(T.exportOptions().export_all_axes);
console.log('PASS: dual-axis export defaults, bidirectional checkbox sync, independent GT/scope request contract');
