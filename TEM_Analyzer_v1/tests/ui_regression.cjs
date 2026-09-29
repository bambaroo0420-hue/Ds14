// Run with Node and @napi-rs/canvas installed (dev/test only).
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const {createCanvas,Image}=require('@napi-rs/canvas');
const root=path.join(__dirname,'..');
const html=fs.readFileSync(path.join(root,'web/index.html'),'utf8');
const elements={};
for(const match of html.matchAll(/id="([^"]+)"/g)){
 let value='';elements[match[1]]={checked:html.includes(`id="${match[1]}" type="checkbox" checked`),showModal(){this.open=true},close(){this.open=false},style:{},classList:{add(){},remove(){}},addEventListener(){},textContent:'',set value(v){value=String(v)},get value(){return value},set innerHTML(v){this.html=v;value=v.match(/value="([^"]*)"/)?.[1]||''},get innerHTML(){return this.html||''}};
}
const rc=createCanvas(320,240);rc.addEventListener=()=>{};rc.setPointerCapture=()=>{};rc.getBoundingClientRect=()=>({left:0,top:0});elements.roiCanvas=rc;elements.roiHost.clientWidth=320;elements.roiHost.clientHeight=240;
const screen=createCanvas(320,240);screen.style={};screen.addEventListener=()=>{};screen.setPointerCapture=()=>{};elements.canvas=screen;
elements.canvasHost.clientWidth=320;elements.canvasHost.clientHeight=240;elements.canvasHost.getBoundingClientRect=()=>({left:0,top:0});
elements.grid.value=4;elements.mlCount.value=3;elements.mlClusters.value=3;elements.mlDistance.value=2;
function fixture(mode){const c=createCanvas(16,8),x=c.getContext('2d');x.fillStyle=mode==='image'?'#444':'black';x.fillRect(0,0,16,8);x.fillStyle='white';if(mode==='left'||mode==='union')x.fillRect(0,0,4,8);if(mode==='right'||mode==='union')x.fillRect(12,0,4,8);return c.toBuffer('image/png')}
const native=Object.getOwnPropertyDescriptor(Image.prototype,'src');
function LocalImage(){let im=new Image();Object.defineProperty(im,'src',{set(url){let mode=url.includes('/images/')?'image':url.includes('layer-mask')?'union':url.includes('/1.png')?'left':'right';setTimeout(()=>native.set.call(im,fixture(mode)),mode==='left'?25:1)}});return im}
const state={images:{a:{name:'synthetic',width:16,height:8}},templates:{empty:{id:'empty',name:'empty',scale_roi:null,text_rois:[]}},selected_template:'empty',layers:[{id:1,name:'A',color:'#0088ff'}],candidates:{a:[{id:1,source:'test',area:32,predicted_iou:.9},{id:2,source:'test',area:32,predicted_iou:.8}]},scale:{}};
const calls=[];
const context=vm.createContext({console,Image:LocalImage,setTimeout:fn=>{queueMicrotask(fn)},ResizeObserver:class{observe(){}},document:{getElementById(id){assert(elements[id],'missing HTML id '+id);return elements[id]},createElement(tag){assert.equal(tag,'canvas');return createCanvas(1,1)},querySelectorAll(){return []}},fetch:async(url,opts)=>{calls.push(url);let data=url.endsWith('/state')?state:url.endsWith('/prompts/grid')?{points:[[2,2],[6,2]]}:url.endsWith('/prompts/ml')?{points:[[10,3]],count:1}:{};return {ok:true,headers:{get:()=> 'application/json'},json:async()=>data}},confirm:()=>true,prompt:()=>null});
vm.runInContext(fs.readFileSync(path.join(root,'web/roi_editor.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'web/app.js'),'utf8'),context);
const run=s=>vm.runInContext(s,context);
(async()=>{
 await new Promise(r=>setTimeout(r,70));
 elements.candidateSelect.value='1';await run('loadMask()');let rgba=run('tint.getContext("2d").getImageData(0,0,16,8).data');assert.equal(rgba[3],255);assert.equal(rgba[12*4+3],0,'mask background must be transparent');
 elements.candidateSelect.value='2';await elements.candidateSelect.onchange();rgba=run('tint.getContext("2d").getImageData(0,0,16,8).data');assert.equal(rgba[3],0);assert.equal(rgba[12*4+3],255,'candidate 2 must show different area');
 elements.candidateSelect.value='1';let slow=run('loadMask()');elements.candidateSelect.value='2';let fast=run('loadMask()');await Promise.all([slow,fast]);rgba=run('tint.getContext("2d").getImageData(0,0,16,8).data');assert.equal(rgba[3],0,'stale mask response must not replace current selection');
 elements.layerSelect.value='1';await elements.layerSelect.onchange();rgba=run('tint.getContext("2d").getImageData(0,0,16,8).data');assert.equal(rgba[3],255);assert.equal(rgba[12*4+3],255,'layer union must show both components');
 await elements.automatic.onclick();assert.equal(run('gridPoints.length'),2);assert(!calls.some(x=>x.includes('/sam/')),'grid preparation must not run SAM');
 await elements.suggestML.onclick();assert.equal(run('mlPoints.length'),1);assert(!calls.some(x=>x.includes('/sam/')),'ML proposal must not run SAM');

 // Sorting changes rows, never the selected candidate identity.
 run("state.candidates.a[0].name='Z';state.candidates.a[1].name='A';state.candidates.a[0].area=90;state.candidates.a[1].area=20");
 elements.candidateSelect.value='2';elements.sortPixel.onclick();assert.equal(run('sortedCandidates()[0].id'),2);elements.sortPixel.onclick();assert.equal(run('sortedCandidates()[0].id'),1);assert.equal(run('selected()'),2);
 elements.sortName.onclick();assert.equal(run('sortedCandidates()[0].id'),2);elements.sortName.onclick();assert.equal(run('sortedCandidates()[0].id'),1);
 // Hide toggles affect rendered pixels without deleting prepared input/masks.
 run('base.width=16;base.height=8;fit=1;zoom=1;panX=0;panY=0;gridPoints=[[8,4]];mlPoints=[];points=[];scaleBar=null');
 elements.showMasks.checked=false;elements.showPrompts.checked=false;run('redraw()');let hidden=screen.getContext('2d').getImageData(1,1,1,1).data;assert.equal(hidden[0],68);
 elements.showMasks.checked=true;run('redraw()');let visible=screen.getContext('2d').getImageData(1,1,1,1).data;assert.notEqual(visible[0],68);assert.equal(run('gridPoints.length'),1);
 elements.scaleLength.value='50';elements.scaleUnit.value='nm';run('setScaleBar([[1,1],[101,1]])');assert(elements.scalePreview.textContent.includes('2.000000 px/nm'));assert(elements.scalePreview.textContent.includes('0.500000 nm/px'));
 // ROI editor uses its own prompts and maps screen input to original pixels.
 elements.candidateSelect.value='1';await elements.roiPrompt.onclick();assert(elements.roiDialog.open);assert.equal(run('roiEditor.parent'),1);assert.deepEqual(Array.from(run('roiEditor.roi')),[0,0,4,8]);
 elements.roiTool.value='positive';const p=run('[roiEditor.pan[0]+2*roiEditor.scale,roiEditor.pan[1]+3*roiEditor.scale]');run(`roiEditor.down({button:0,pointerId:1,clientX:${p[0]},clientY:${p[1]}})`);assert.equal(run('roiEditor.points[0][0]'),2);assert.equal(run('roiEditor.points[0][1]'),3);assert.equal(run('points.length'),0);
 let payload;context.capturePayload=x=>{payload=x};await run("roiEditor.api=async (path,body)=>{capturePayload(body);return {id:3}};roiEditor.onSaved=async()=>{};roiEditor.run()");assert.equal(payload.parent,1);assert.equal(payload.image_id,'a');assert.equal(payload.points[0][2],1);assert(!elements.roiDialog.open);

 // Image navigation restores the selected image's scale and its own draft points.
 state.images.b={name:'second',width:16,height:8};state.candidates.b=[];state.scale.b={bar:[[1,1],[11,1]],length:20,unit:'nm',nm_per_px:2,confirmed:true};
 await elements.nextImage.onclick();assert.equal(run('current'),'b');assert.equal(elements.scaleLength.value,'20');assert.equal(run('gridPoints.length'),0);assert(elements.scaleInfo.textContent.includes('0.500000 px/nm'));
 await elements.prevImage.onclick();assert.equal(run('current'),'a');assert.equal(run('gridPoints.length'),1);assert.equal(run('scaleBar'),null);
 assert((html.match(/<details/g)||[]).length>=5);console.log('PASS: binary transparency, candidate switch, stale-response guard, layer union, grid/ML prepare without SAM, collapsible sections, sorting, visibility, scale preview, independent ROI coordinates');
})().catch(e=>{console.error(e);process.exitCode=1});
