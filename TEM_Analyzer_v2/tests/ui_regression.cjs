// Run with Node and @napi-rs/canvas installed (dev/test only).
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const {createCanvas,Image}=require('@napi-rs/canvas');
const root=path.join(__dirname,'..');
const html=fs.readFileSync(path.join(root,'web/index.html'),'utf8');
const elements={};
for(const match of html.matchAll(/id="([^"]+)"/g)){
 let value='';elements[match[1]]={checked:html.includes(`id="${match[1]}" type="checkbox" checked`),showModal(){this.open=true},close(){this.open=false},style:{},classList:{add(){},remove(){},toggle(){}},addEventListener(){},textContent:'',set value(v){value=String(v)},get value(){return value},set innerHTML(v){this.html=v;value=v.match(/value="([^"]*)"/)?.[1]||''},get innerHTML(){return this.html||''}};
}
const rc=createCanvas(320,240);rc.addEventListener=()=>{};rc.setPointerCapture=()=>{};rc.getBoundingClientRect=()=>({left:0,top:0});elements.roiCanvas=rc;elements.roiHost.clientWidth=320;elements.roiHost.clientHeight=240;
const screen=createCanvas(320,240);screen.style={};screen.addEventListener=()=>{};screen.setPointerCapture=()=>{};elements.canvas=screen;
elements.canvasHost.clientWidth=320;elements.canvasHost.clientHeight=240;elements.canvasHost.getBoundingClientRect=()=>({left:0,top:0});
elements.grid.value=4;elements.mlCount.value=3;elements.mlClusters.value=3;elements.mlDistance.value=2;
function fixture(mode){const c=createCanvas(16,8),x=c.getContext('2d');x.fillStyle=mode==='image'?'#444':'black';x.fillRect(0,0,16,8);x.fillStyle='white';if(mode==='left'||mode==='union')x.fillRect(0,0,4,8);if(mode==='right'||mode==='union')x.fillRect(12,0,4,8);return c.toBuffer('image/png')}
const native=Object.getOwnPropertyDescriptor(Image.prototype,'src');
function LocalImage(){let im=new Image();Object.defineProperty(im,'src',{set(url){let mode=url.includes('/preprocessing/')?(url.includes('mode=processed')?'cleaned':'image'):url.includes('/images/')?'image':url.includes('layer-mask')?'union':url.includes('/1.png')?'left':'right';setTimeout(()=>native.set.call(im,fixture(mode)),mode==='left'?25:1)}});return im}
const state={images:{a:{name:'synthetic',width:16,height:8}},templates:{empty:{id:'empty',name:'empty',scale_roi:null,text_rois:[]}},selected_template:'empty',layers:[{id:1,name:'A',color:'#0088ff'}],candidates:{a:[{id:1,source:'test',area:32,predicted_iou:.9},{id:2,source:'test',area:32,predicted_iou:.8}]},scale:{}};
const calls=[];
const windowStub={dispatchEvent(){},addEventListener(){}};
const context=vm.createContext({console,Image:LocalImage,setTimeout:fn=>{queueMicrotask(fn)},ResizeObserver:class{observe(){}},document:{addEventListener(){},getElementById(id){assert(elements[id],'missing HTML id '+id);return elements[id]},createElement(tag){assert.equal(tag,'canvas');return createCanvas(1,1)},querySelectorAll(){return []}},fetch:async(url,opts)=>{calls.push(url);let data=url.endsWith('/state')?state:url.endsWith('/prompts/grid')?{points:[[2,2],[6,2]]}:url.endsWith('/prompts/ml')?{points:[[10,3]],count:1}:{};return {ok:true,headers:{get:()=> 'application/json'},json:async()=>data}},confirm:()=>true,prompt:()=>null});
context.window=windowStub;context.Event=class Event{constructor(type){this.type=type}};
vm.runInContext(fs.readFileSync(path.join(root,'web/roi_editor.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'web/app.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'web/v2.js'),'utf8'),context);
const run=s=>vm.runInContext(s,context);
(async()=>{
 await run('initialReady');
 // This suite exercises the legacy fixed-template controls explicitly enabled.
 state.legacy_templates_enabled=true;
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
 let payload;context.capturePayload=x=>{payload=x};await run("roiEditor.api=async (path,body)=>{capturePayload(body);return path==='sam/prompt'?{preview_token:'preview123',area:20}:{id:3}};roiEditor.onSaved=async()=>{};roiEditor.run()");assert.equal(payload.parent,1);assert.equal(payload.image_id,'a');assert.equal(payload.points[0][2],1);assert.equal(payload.preview,true);assert(elements.roiDialog.open,'inference must leave review dialog open');assert.equal(run('roiEditor.preview.token'),'preview123');assert(!elements.roiAccept.disabled,'accept must be enabled after preview');await run('roiEditor.accept()');assert(!elements.roiDialog.open);

 // Image navigation restores the selected image's scale and its own draft points.
 state.images.b={name:'second',width:16,height:8};state.candidates.b=[];state.scale.b={bar:[[1,1],[11,1]],length:20,unit:'nm',nm_per_px:2,confirmed:true};
 await elements.nextImage.onclick();assert.equal(run('current'),'b');assert.equal(elements.scaleLength.value,'20');assert.equal(run('gridPoints.length'),0);assert(elements.scaleInfo.textContent.includes('0.500000 px/nm'));
 await elements.prevImage.onclick();assert.equal(run('current'),'a');assert.equal(run('gridPoints.length'),1);assert.equal(run('scaleBar'),null);

 // Actual batch UI handler, results, review state and before/after canvas switch.
 const oldFetch=context.fetch;let batchBody;
 context.fetch=async(url,opts)=>{if(url.endsWith('/preprocessing/apply')){batchBody=JSON.parse(opts.body);state.preprocessing={a:{regions_applied:true,excluded_pixels:12,scale_status:'proposed',reviewed:false},b:{scale_status:'failed',reviewed:false,last_error:'검출 실패'}};return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({count:2})}}if(url.endsWith('/preprocessing/confirm')){state.preprocessing.a.reviewed=true;return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({reviewed:true})}}return oldFetch(url,opts)};
 elements.scaleLength.value='50';elements.scaleUnit.value='nm';await elements.batchApply.onclick();assert.equal(batchBody.length,50);assert.equal(batchBody.image_ids,null);assert.equal(batchBody.apply_regions,true);assert(elements.batchSummary.textContent.includes('실패 1'));assert(elements.batchResults.innerHTML.includes('검출·처리 실패'));
 elements.showMasks.checked=false;elements.showPrompts.checked=false;elements.batchView.value='processed';await elements.batchView.onchange();run('scaleBar=null;fit=1;zoom=1;panX=0;panY=0;redraw()');assert.equal(screen.getContext('2d').getImageData(1,1,1,1).data[0],0);
 elements.batchView.value='original';await elements.batchView.onchange();assert.equal(screen.getContext('2d').getImageData(1,1,1,1).data[0],68);
 await elements.batchConfirm.onclick();assert(elements.batchSummary.textContent.includes('검수 완료 1'));assert(elements.batchConfirm.disabled);

 // Regression: unsaved scale ROI + multiple text ROIs survive image navigation
 // and SAM prompt clearing, then all appear in the actual batch request.
 run('scaleDraft=[1,4,10,7];captureTemplateDraft();textDraft=[[0,0,3,2]];captureTemplateDraft();textDraft=[[10,0,15,2]];captureTemplateDraft()');
 const before=JSON.stringify(run('currentTemplateDraft()'));
 await elements.nextImage.onclick();assert.equal(JSON.stringify(run('currentTemplateDraft()')),before);elements.clearMarks.onclick();assert.equal(JSON.stringify(run('currentTemplateDraft()')),before);
 assert(elements.regionSummary.textContent.includes('스케일 1개 + 글씨 제외 2개'));
 elements.scaleLength.value='50';await elements.batchApply.onclick();assert.equal(batchBody.template.text_rois.length,2);assert.deepEqual(batchBody.template.scale_roi,[1/16,4/8,10/16,7/8]);
 assert(elements.batchResults.innerHTML.includes('<tr'));assert.equal(elements.batchResults.innerHTML,elements.batchLargeRows.innerHTML);
 // v2: preserve selection while inference is pending; hide replaced/deleted candidates.
 await elements.prevImage.onclick();let release;context.waitForWork=new Promise(r=>{release=r});const pending=run('task(()=>waitForWork)');await elements.nextImage.onclick();assert.equal(run('current'),'a','busy task must block image navigation');release();await pending;
 run("state.candidates.a.push({id:90,source:'old',area:1,active:false},{id:91,source:'deleted',area:1,deleted:true})");assert(!Array.from(run('sortedCandidates().map(c=>c.id)')).includes(90));assert(!Array.from(run('sortedCandidates().map(c=>c.id)')).includes(91));
 let assignment;const fetchBeforeAssign=context.fetch;context.fetch=async(url,opts)=>{if(url.endsWith('/layers/assign')){assignment=JSON.parse(opts.body);return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({})}}return fetchBeforeAssign(url,opts)};
 run('state.candidates.a[1].parent=1');elements.candidateSelect.value='2';elements.layerSelect.value='1';elements.assignMode.value='replace';await elements.assign.onclick();assert.equal(assignment.mode,'replace');assert.equal(assignment.replace_id,1);assert.equal(assignment.candidate_id,2);assert.equal(assignment.image_id,'a');
 // The exact reported regression: unsaved dragged ROI must precede Grid requests.
 const fetchBeforeRegions=context.fetch,sequence=[];context.fetch=async(url,opts)=>{if(url.endsWith('/preprocessing/apply')){sequence.push('apply');const b=JSON.parse(opts.body),id=b.image_ids[0];const rec={template:b.template,regions_applied:true};state.preprocessing[id]=rec;return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({count:1,results:{[id]:rec}})}}if(url.endsWith('/prompts/grid')){sequence.push('grid');return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({points:[[12,6]]})}}return fetchBeforeRegions(url,opts)};
 run("templateDraft={id:'dragged',name:'dragged',scale_roi:null,text_rois:[]};textDraft=[[0,0,8,4]];gridPoints=[[1,1],[12,6]];captureTemplateDraft()");assert.equal(run('gridPoints.length'),1,'drag must remove already prepared excluded points');await elements.automatic.onclick();assert.deepEqual(sequence,['apply','grid']);assert.equal(run('gridPoints[0][0]'),12);
 // Layer addition no longer relies on prompt text or cancels on an empty name.
 const oldPrompt=context.prompt;context.prompt=()=>{throw Error('layer add must not open a name prompt')};let newLayerBody;const fetchBeforeLayer=context.fetch;context.fetch=async(url,opts)=>{if(url.endsWith('/layers')){newLayerBody=JSON.parse(opts.body);state.layers.push({id:3,name:'Layer 3',color:'#0088ff'});return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({id:3,name:'Layer 3'})}}return fetchBeforeLayer(url,opts)};await elements.newLayer.onclick();assert.deepEqual(newLayerBody,{});assert.equal(elements.layerSelect.value,'3');context.prompt=oldPrompt;
 // Clear button removes project image state and the displayed base canvas.
 const fetchBeforeDelete=context.fetch;context.fetch=async(url,opts)=>{if(url==='/api/images'&&opts.method==='DELETE'){state.images={};state.candidates={};state.scale={};state.preprocessing={};return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({deleted:2})}}return fetchBeforeDelete(url,opts)};
 await elements.clearLoadedImages.onclick();assert.equal(run('current'),null);assert.equal(run('base.naturalWidth'),0);assert.equal(run('Object.keys(imageDrafts).length'),0);
 assert((html.match(/<details/g)||[]).length>=5);console.log('PASS: ROI preview/accept, auto layer naming, dragged ROI before Grid, binary transparency, candidate switch, stale-response guard, layer union, grid/ML prepare without SAM, collapsible sections, sorting, visibility, scale preview, independent ROI coordinates, v2 busy navigation lock, inactive filtering, parent replacement payload');
})().catch(e=>{console.error(e);process.exitCode=1});

