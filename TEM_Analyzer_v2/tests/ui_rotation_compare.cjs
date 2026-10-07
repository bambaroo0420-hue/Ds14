const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
// Minimal DOM-contract fixture, no external package. Actual browser checked separately.
const ids={};
class Element{
 constructor(){this.dataset={};this.value='';this.buttons=[]}
 set innerHTML(html){this.html=html;for(const m of html.matchAll(/id="([^"]+)"/g))ids[m[1]]=new Element();this.buttons=[...html.matchAll(/data-rotation-method="(\d+)"/g)].map(m=>{const b=new Element();b.dataset.rotationMethod=m[1];return b})}
 get innerHTML(){return this.html||''}
 querySelectorAll(){return this.buttons}
 before(){} append(){} showModal(){this.open=true} close(){this.open=false}
}
for(const id of ['rotationPreview','rotationMode','rotationEdge','rotationROI','rotationPoints'])ids[id]=new Element();
const d={body:new Element(),createElement:()=>new Element(),getElementById:id=>ids[id],querySelector:s=>s==='[data-rotation-method]'?ids.rotationMethodRows.buttons[0]:ids[s.slice(1)]};
const ctx=vm.createContext({document:d,JSON,Error});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/modules/rotation_compare.js'),'utf8').replace('export function','function')+'\nthis.mount=mountRotationComparison;',ctx);
const calls=[],errors=[];let config={scope_id:'target',mode:'auto',edge:'top',points:[]},response;
const T={current:'a',state:{revision:1,images:{a:{name:'a.png'}}},escape:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;'),say:()=>{},refresh:async()=>{},task:async f=>{try{return await f()}catch(e){errors.push(e.message)}},api:async(path,body)=>{calls.push({path,body});return typeof response==='function'?response():response}};
const instance=ctx.mount(T,()=>config);
const result=()=>({max_angle_gap_deg:12,note:'not GT',rows:[{name:'<unsafe>',status:'failed',error:'no edge'},{name:'points',status:'proposed',angle_deg:45,residual_px:0,point_count:2,warnings:['not expert GT'],config:{...config,mode:'points',points:[[10,10],[30,30]],roi:null}}]});
(async()=>{
 response=result();await instance.button.onclick();assert.equal(calls.length,1);assert(instance.dialog.open);assert(!ids.rotationMethodRows.innerHTML.includes('<unsafe>'));assert(ids.rotationMethodRows.innerHTML.includes('no edge'));
 T.state.revision=2;await d.querySelector('[data-rotation-method]').onclick();assert.equal(calls.length,1);assert(errors.at(-1).includes('입력이 바뀌'));
 response=result();await instance.button.onclick();await d.querySelector('[data-rotation-method]').onclick();assert.equal(calls.at(-1).path,'workflow/rotation/preview');assert(!calls.some(c=>c.path.includes('/confirm')));assert.equal(d.querySelector('#rotationMode').value,'points');assert.equal(d.querySelector('#rotationPoints').value,'[[10,10],[30,30]]');assert(!instance.dialog.open);
 let release;response=()=>new Promise(resolve=>release=resolve);const pending=instance.button.onclick();T.current='b';release(result());await pending;assert(errors.at(-1).includes('비교 중 입력'));assert(!instance.dialog.open);
 console.log('PASS: rotation comparison read-only request, failure rows/escaping, stale adoption/response guards, separate preview without confirmation');
})().catch(e=>{console.error(e);process.exitCode=1});
