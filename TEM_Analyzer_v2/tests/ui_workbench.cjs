// Logic contracts for final-review fixes; actual browser checks are documented separately.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const source=name=>fs.readFileSync(path.join(__dirname,'../web/modules',name),'utf8');
const elements={},events={};
class El{
 constructor(id=''){this.id=id;this.value='';this.textContent='';this.style={};this.dataset={};this.checked=false;this.classList={toggle(){},add(){},remove(){}};this.attrs={};this.handlers={};this.children=[]}
 setAttribute(k,v){this.attrs[k]=v} addEventListener(k,v){this['on'+k]=v;(this.handlers[k]||=[]).push(v)}
 closest(selector){return selector==='.mask-drag-handle'?null:selector==='[data-id]'?this:scroll} before(){} append(){}
 querySelector(){return {}} // Handles already exist in this minimal row fixture.
 querySelectorAll(){return this.id==='candidateRows'?rows:[]}
}
const get=id=>elements[id]||(elements[id]=new El(id));
const scroll=new El('scroll'),rows=[1,2].map(id=>{const e=new El();e.dataset.id=String(id);return e});
const docEvents={};let underPointer=null;
const document={getElementById:get,createElement:()=>new El(),addEventListener(k,v){(docEvents[k]||=[]).push(v)},elementFromPoint:()=>underPointer};
const window={addEventListener(k,v){(events[k]||=[]).push(v)},dispatchEvent(){}};
const T={current:'a',state:{manual_groups:{}},selectedCandidate:1,candidates:()=>[{id:1},{id:2}],busy:false,chooseCandidate(v){this.selectedCandidate=+v},task:fn=>fn(),escape:x=>x,say:v=>T.message=v,promptDraft:()=>({feature_settings:{}}),setPromptDraft(){}};
const context=vm.createContext({document,window,Event:class{},T,Set,Map,structuredClone});
vm.runInContext(source('selection.js').replaceAll('export function','function')+'\nthis.selection=mountSelection(T)',context);
context.selection.render();assert.match(get('maskSelectionCount').textContent,/1개 대상/);assert.equal(rows[0].attrs['aria-selected'],'true');
get('candidateRows').onclick({target:rows[0]});get('candidateRows').onclick({target:rows[1],ctrlKey:true});assert.deepEqual(Array.from(context.selection.ids()),[1,2]);assert.match(get('maskSelectionCount').textContent,/2개 선택/);
const drop=new El();drop.dataset.dropLayer='2';drop.closest=()=>drop;get('layerDrops').children=[drop];underPointer=drop;
const handle={closest:()=>rows[0],setPointerCapture(){}};
const event={target:{closest:()=>handle},button:0,pointerId:9,preventDefault(){},stopPropagation(){},clientX:100,clientY:200};
let assigned;T.api=async(path,body)=>{assigned={path,body}};T.refresh=async()=>{};
for(const fn of get('candidateRows').handlers.pointerdown)fn(event);
for(const fn of docEvents.pointerup)fn(event);
assert.equal(assigned.path,'workflow/masks/bulk');assert.equal(assigned.body.layer_id,2);assert.deepEqual(Array.from(assigned.body.candidate_ids),[1,2]);assert.equal(rows[0].draggable,true);

vm.runInContext(source('manual_groups.js').replaceAll('export function','function')+'\nmountManualGroups(T)',context);
T.setPromptDraft({manual_groups:[{name:'M1',points:[[2,3,1]]}],auto_policy:'grid_features',grid:4,feature_settings:{method:'sobel',count:7,profile_angle:null,denoise:'median'}});
assert.equal(get('recipeAutoPolicy').value,'grid_features');assert.equal(get('grid').value,4);assert.equal(get('featureMethod').value,'sobel');assert.equal(get('mlCount').value,7);assert.equal(get('profileAngle').value,'');assert.equal(get('promptDenoise').value,'median');assert.equal(T.promptDraft().manual_groups[0].name,'M1');

const line=source('metrology.js').split(/\r?\n/).find(s=>s.includes("$('rotationUseROI').onclick="));
assert(line);context.$=get;get('rotationROI').value='[0.1,0.2,0.8,0.7]';T.boundaryROI=null;vm.runInContext(line,context);get('rotationUseROI').onclick();assert.equal(get('rotationROI').value,'[0.1,0.2,0.8,0.7]');assert.match(T.message,/먼저/);
T.boundaryROI=[.2,.3,.7,.9];get('rotationUseROI').onclick();assert.equal(get('rotationROI').value,'[0.2,0.3,0.7,0.9]');
assert(source('workbench.js').includes('prepareComparisonImage(root+'));assert(source('workbench.js').includes('T.state.revision!==revision'));
console.log('PASS: workbench selection count, multi-selection, pointer-handle layer assignment, Recipe policy/feature restore, empty/drawn rotation ROI, bounded evidence loader and stale guard');
