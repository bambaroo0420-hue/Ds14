const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
// Minimal DOM contract; real image loading, canvas and clicks are audited separately.
const ids={},listeners={};
class Element {
 constructor(){this.value='';this.options=[];this.dataset={};this.checked=false;this.disabled=false;this.naturalWidth=480;this.buttons=[];this.width=420;this.height=200}
 set innerHTML(html){this.html=html;for(const m of html.matchAll(/<(\w+)[^>]*id="([^"]+)"[^>]*>/g)){const e=new Element();e.value=m[0].match(/\bvalue="([^"]*)"/)?.[1]||'';ids[m[2]]=e;}this.buttons=[...html.matchAll(/data-brush-lock="(\d+)"/g)].map(m=>{const e=new Element();e.dataset.brushLock=m[1];return e;});this.options=[...html.matchAll(/<option value="([^"]+)"/g)].map(m=>({value:m[1]}));}
 get innerHTML(){return this.html||''}
 querySelectorAll(){return this.buttons} before(){} prepend(){} append(){} add(o){this.options.push(o)}
 addEventListener(name,fn){this[name]=fn} showModal(){this.open=true} close(){this.open=false}
 getContext(){return new Proxy({},{get:()=>()=>{},set:()=>true})}
}
for(const id of ['canvasHost','tool','boundary','applyBrush'])ids[id]=new Element();
const document={body:new Element(),createElement:()=>new Element(),getElementById:id=>ids[id]};
const window={addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)};
const ctx=vm.createContext({document,window,Option:class {constructor(text,value){this.text=text;this.value=value}}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/modules/gap_bridge.js'),'utf8').replace('export function','function')+'\nthis.mount=mountGapBridge;',ctx);
let response,applied=false;const calls=[],errors=[];
const T={busy:false,current:'a',selectedCandidate:7,state:{revision:0,layers:[{id:1,name:'A',locked:true},{id:2,name:'B'}],candidates:{a:[{id:7,parent:6,layer_id:null},{id:6,layer_id:1}]}},escape:String,say:()=>{},
 refresh:async()=>{for(const f of listeners['tem:refreshed']||[])f()},
 task:async f=>{try{return await f()}catch(e){errors.push(e.message)}finally{for(const fn of listeners['tem:idle']||[])fn()}},
 api:async(route,body)=>{calls.push({route,body});if(route==='v2/lock'){T.state.layers.find(l=>l.id===body.layer_id).locked=body.locked;T.state.revision++;return {}}if(route.endsWith('/apply')){applied=true;return {changed_pixels:40,created:[{id:8},{id:9}]}}return response;}};
ctx.mount(T);
const proposal=()=>({token:'test-token',changed_pixels:40,reports:[{traces:[{profile:{coordinate:[10,11,12],gradient:[.1,.8,.1],chosen:11,axis:'vertical',scan:8}}],skipped:{},note:'synthetic'}]});
(async()=>{
 assert(ids.applyBrush.disabled,'nested draft inherits layer lock');assert(ids.tool.options.some(o=>o.value==='roi'));
 await ids.brushLocks.buttons[0].onclick();assert(!ids.applyBrush.disabled);assert.equal(calls[0].route,'v2/lock');
 response=proposal();ids.gapAxis.value='auto';await ids.gapPreview.onclick();
 ids.gapConfirm.checked=true;ids.gapConfirm.onchange();assert(ids.gapApply.disabled,'not usable before image loads');
 ids.gapPreviewImage.onload();assert(!ids.gapApply.disabled);
 ids.gapPreviewImage.onerror();assert(ids.gapApply.disabled,'failed image must block commit');
 await ids.gapPreview.onclick();ids.gapPreviewImage.onload();ids.gapConfirm.checked=true;ids.gapConfirm.onchange();assert(!ids.gapApply.disabled);
 await ids.gapApply.onclick();assert(applied);assert.equal(calls.at(-1).body.confirmed_two_layers,true);assert(ids.gapSummary.textContent.includes('적용 완료'));assert(ids.gapApply.disabled);
 await ids.gapPreview.onclick();ids.gapPreviewImage.onload();ids.gapConfirm.checked=true;ids.gapConfirm.onchange();T.state.revision++;await T.refresh();assert(ids.gapApply.disabled);
 ids.gapUseROI.checked=true;await ids.gapPreview.onclick();assert(errors.at(-1).includes('ROI'));
 ids.gapUseROI.checked=false;response={...proposal(),changed_pixels:0};await ids.gapPreview.onclick();ids.gapPreviewImage.onload();ids.gapConfirm.checked=true;ids.gapConfirm.onchange();assert(ids.gapApply.disabled);
 console.log('PASS: gap preview/apply, review and image readiness gates, nested brush lock, error/stale/zero-change guards, ROI mode, completion message');
})().catch(e=>{console.error(e);process.exitCode=1});
