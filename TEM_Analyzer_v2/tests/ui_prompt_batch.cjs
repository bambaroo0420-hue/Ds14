// Focused DOM-contract test, no browser replacement. Real UI proof is separate.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const ids={},events={},all=[];
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.disabled=false;this.checked=false;this.value='';all.push(this)}
 set innerHTML(html){this.html=html;for(const m of html.matchAll(/id="([^"]+)"/g))ids[m[1]]=new Element('generated');if(this.tag==='generated')this.value=html.match(/value="([^"]+)"/)?.[1]||''}
 get innerHTML(){return this.html||''}
 append(...xs){this.children.push(...xs)}
 after(){}
 closest(){return this}
 setAttribute(k,v){this[k]=v}
 replaceChildren(...xs){this.children=xs}
 querySelectorAll(selector){let items=[];const walk=e=>{if(e.tag==='input'&&e.checked)items.push(e);e.children.forEach(walk)};walk(this);return selector==='input:checked'?items:[]}
 showModal(){this.open=true}
 close(){this.open=false}
}
ids.batchPromptSource=new Element('select');ids.batchScope=new Element('select');ids.batchScope.value='selected';
const window={addEventListener:(n,f)=>(events[n]??=[]).push(f),dispatchEvent:e=>(events[e.type]||[]).forEach(f=>f())};
const document={body:new Element('body'),getElementById:id=>ids[id],createElement:tag=>new Element(tag)};
const calls=[];const records={a:{draft_hash:'a1',signature:'sig_a',preset_id:'recipe',method:'normalized',ecc_score:null,warnings:[],draft:{auto_points:[[10,10]],manual_points:[]}}};
const T={busy:false,current:'a',selectedImages:['a'],state:{images:{a:{name:'a.png'}},prompt_presets:{recipe:{id:'recipe'}},prompt_transfers:records},escape:s=>s,say:()=>{},confirm:async()=>true,refresh:async()=>window.dispatchEvent({type:'tem:refreshed'}),api:async(route,body,method)=>{calls.push({route,body,method});return records.a},task:async fn=>{if(T.busy)return;T.busy=true;const controls=all.map(e=>[e,e.disabled]);for(const [e]of controls)e.disabled=true;try{await fn()}finally{T.busy=false;for(const[e,d]of controls)e.disabled=d;window.dispatchEvent({type:'tem:idle'})}}};
const context=vm.createContext({document,window,Event:class{constructor(type){this.type=type}},Map,console});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/modules/prompt_batch.js'),'utf8').replace('export function','function')+'\nthis.mount=mountPromptBatch;',context);
const moduleUI=context.mount(T),row=()=>ids.promptTransferRows.children[0],check=()=>row().children[0].children[0],view=()=>row().children[3].children[0];
(async()=>{
 assert(check().disabled,'cannot confirm an unseen image');
 await view().onclick();
 assert(ids.markPromptViewed.disabled,'global task restore must not bypass image load gate');
 ids.markPromptViewed.onclick();assert(check().disabled,'handler also guards unloaded image');
 ids.promptBatchPreviewImage.onload();assert(!ids.markPromptViewed.disabled);
 ids.markPromptViewed.onclick();assert(check().checked&&!check().disabled);
 check().checked=false;check().onchange();moduleUI.render();assert(!check().checked,'refresh preserves deliberate deselection');
 check().checked=true;check().onchange();await ids.confirmPromptBatch.onclick();assert(calls.some(x=>x.route.endsWith('/confirm')&&x.body.entries[0].signature==='sig_a'));
 assert(!calls.some(x=>x.route.includes('jobs/start')),'preview/confirm never start SAM');
 await view().onclick();ids.promptBatchPreviewImage.onerror();assert(ids.markPromptViewed.disabled);
 records.a.superseded_by='new-job';moduleUI.render();assert(check().disabled&&!check().checked&&view().disabled);
 await ids.preparePromptBatch.onclick();const job=calls.find(x=>x.route.endsWith('jobs/start'));assert.equal(job.body.steps.join(','),'prompt_transfer');
 console.log('PASS: prompt preview image-load/idle gate, error guard, per-image confirmation, deselection retention, stale draft, prepare-only job');
})().catch(e=>{console.error(e);process.exitCode=1});
