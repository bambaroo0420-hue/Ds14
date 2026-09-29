/* Independent ROI prompt editor. All stored coordinates are original image pixels. */
class ROIEditor {
 constructor({api,onSaved}) {
  this.api=api;this.onSaved=onSaved;this.busy=false;
  this.el=id=>document.getElementById(id);this.dialog=this.el('roiDialog');
  this.canvas=this.el('roiCanvas');this.ctx=this.canvas.getContext('2d');this.host=this.el('roiHost');
  this.el('roiClose').onclick=()=>{if(!this.busy)this.dialog.close()};
  this.dialog.addEventListener('cancel',e=>{if(this.busy)e.preventDefault()});
  this.el('roiClear').onclick=()=>{if(this.busy)return;this.points=[];this.box=null;this.draw()};
  this.el('roiReset').onclick=()=>this.fit();
  this.el('roiShowPoints').onchange=()=>this.draw();this.el('roiShowMask').onchange=()=>this.draw();
  this.el('roiRun').onclick=()=>this.run();
  this.canvas.addEventListener('pointerdown',e=>this.down(e));
  this.canvas.addEventListener('pointermove',e=>this.move(e));
  this.canvas.addEventListener('pointerup',e=>this.up(e));
  this.canvas.addEventListener('pointercancel',()=>{this.drag=null;this.draw()});
  this.canvas.addEventListener('contextmenu',e=>{e.preventDefault();if(this.busy)return;const p=this.coord(e);let best=-1,d=12/this.scale;this.points.forEach((q,i)=>{const v=Math.hypot(q[0]-p[0],q[1]-p[1]);if(v<d){d=v;best=i}});if(best>=0)this.points.splice(best,1);this.draw()});
  this.canvas.addEventListener('wheel',e=>{e.preventDefault();if(this.busy)return;const p=this.coord(e),r=this.canvas.getBoundingClientRect();this.scale=Math.max(.02,Math.min(50,this.scale*(e.deltaY<0?1.15:1/1.15)));this.pan=[e.clientX-r.left-p[0]*this.scale,e.clientY-r.top-p[1]*this.scale];this.draw()},{passive:false});
  new ResizeObserver(()=>{if(this.dialog.open)this.fit()}).observe(this.host);
 }
 async open(imageId,parent,image) {
  this.imageId=imageId;this.parent=parent;this.image=image;this.points=[];this.box=null;this.drag=null;
  this.el('roiError').textContent='';
  const mask=await new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(Error('부모 마스크를 읽을 수 없습니다.'));im.src=`/api/masks/${imageId}/${parent}.png?${Date.now()}`});
  this.overlay=document.createElement('canvas');this.overlay.width=mask.width;this.overlay.height=mask.height;
  const x=this.overlay.getContext('2d');x.drawImage(mask,0,0);const d=x.getImageData(0,0,mask.width,mask.height);
  let x0=mask.width,y0=mask.height,x1=0,y1=0;
  for(let i=0;i<d.data.length;i+=4){const inside=d.data[i]>127;if(inside){const px=i/4%mask.width,py=Math.floor(i/4/mask.width);x0=Math.min(x0,px);y0=Math.min(y0,py);x1=Math.max(x1,px+1);y1=Math.max(y1,py+1)}d.data[i]=30;d.data[i+1]=220;d.data[i+2]=170;d.data[i+3]=inside?90:0}
  if(x1<=x0||y1<=y0)throw Error('비어 있는 후보는 재분할할 수 없습니다.');
  x.putImageData(d,0,0);this.roi=[x0,y0,x1,y1];this.bounds=[Math.max(0,x0-16),Math.max(0,y0-16),Math.min(image.width,x1+16),Math.min(image.height,y1+16)];
  this.el('roiTitle').textContent=`후보 #${parent} 내부 재분할`;this.dialog.showModal();this.fit();
 }
 fit(){if(!this.image)return;this.canvas.width=Math.max(1,this.host.clientWidth);this.canvas.height=Math.max(1,this.host.clientHeight);const [x0,y0,x1,y1]=this.bounds;this.scale=Math.min(this.canvas.width/(x1-x0),this.canvas.height/(y1-y0))*.92;this.pan=[(this.canvas.width-(x0+x1)*this.scale)/2,(this.canvas.height-(y0+y1)*this.scale)/2];this.draw()}
 coord(e){const r=this.canvas.getBoundingClientRect();return [(e.clientX-r.left-this.pan[0])/this.scale,(e.clientY-r.top-this.pan[1])/this.scale]}
 clamp(p){return [Math.max(0,Math.min(this.image.width,p[0])),Math.max(0,Math.min(this.image.height,p[1]))]}
 inside(p){return p[0]>=this.roi[0]&&p[0]<this.roi[2]&&p[1]>=this.roi[1]&&p[1]<this.roi[3]}
 down(e){if(this.busy||e.button!==0)return;const p=this.coord(e),mode=this.el('roiTool').value;this.canvas.setPointerCapture(e.pointerId);if(mode==='view')this.drag={mode,start:[e.clientX,e.clientY],pan:[...this.pan]};else if(mode==='box'||mode==='roi')this.drag={mode,start:this.clamp(p),now:this.clamp(p)};else if(this.inside(p)){this.points.push([...p,mode==='negative'?0:1]);this.el('roiError').textContent=''}else this.el('roiError').textContent='노란색 ROI 안에 점을 찍으세요.';this.draw()}
 move(e){if(!this.drag||this.busy)return;if(this.drag.mode==='view')this.pan=[this.drag.pan[0]+e.clientX-this.drag.start[0],this.drag.pan[1]+e.clientY-this.drag.start[1]];else this.drag.now=this.clamp(this.coord(e));this.draw()}
 up(e){if(!this.drag||this.busy)return;const d=this.drag;this.drag=null;if(d.mode!=='view'){const p=this.clamp(this.coord(e)),r=[Math.floor(Math.min(d.start[0],p[0])),Math.floor(Math.min(d.start[1],p[1])),Math.ceil(Math.max(d.start[0],p[0])),Math.ceil(Math.max(d.start[1],p[1]))];if(r[2]-r[0]>=2&&r[3]-r[1]>=2){if(d.mode==='roi'){this.roi=r;this.points=this.points.filter(p=>this.inside(p));this.box=null;this.el('roiError').textContent='ROI 밖의 점과 기존 box를 제거했습니다.'}else if(r[0]>=this.roi[0]&&r[1]>=this.roi[1]&&r[2]<=this.roi[2]&&r[3]<=this.roi[3]){this.box=r;this.el('roiError').textContent=''}else this.el('roiError').textContent='SAM box는 노란색 ROI 안에 지정하세요.'}}this.draw()}
 draw(){if(!this.image)return;const x=this.ctx;x.clearRect(0,0,this.canvas.width,this.canvas.height);x.save();x.translate(...this.pan);x.scale(this.scale,this.scale);x.drawImage(this.image,0,0);if(this.el('roiShowMask').checked)x.drawImage(this.overlay,0,0);
  const rect=(r,color)=>{if(!r)return;x.strokeStyle=color;x.lineWidth=2/this.scale;x.strokeRect(r[0],r[1],r[2]-r[0],r[3]-r[1])};rect(this.roi,'#ffdd36');
  if(this.el('roiShowPoints').checked){rect(this.box,'#ae87ff');for(const p of this.points){x.fillStyle=p[2]?'#20ff83':'#ff5471';x.beginPath();x.arc(p[0],p[1],5/this.scale,0,Math.PI*2);x.fill()}}
  if(this.drag&&this.drag.mode!=='view')rect([...this.drag.start,...this.drag.now],'white');x.restore();
  this.el('roiInfo').textContent=`ROI [${this.roi.join(', ')}] · 양성 ${this.points.filter(p=>p[2]).length} / 음성 ${this.points.filter(p=>!p[2]).length} · box ${this.box?1:0} · 휠 확대 / 보기·이동 드래그 / 우클릭 점 삭제`;
 }
 async run(){if(this.busy)return;if(!this.points.some(p=>p[2]===1)&&!this.box){this.el('roiError').textContent='양성점 또는 SAM box를 먼저 지정하세요.';return}this.busy=true;this.el('roiRun').disabled=true;this.el('roiClose').disabled=true;this.el('roiError').textContent='SAM 재분할 중…';try{const result=await this.api('sam/prompt',{image_id:this.imageId,parent:this.parent,roi:[...this.roi],points:this.points.map(p=>[...p]),box:this.box?[...this.box]:null});await this.onSaved(result);this.dialog.close()}catch(e){this.el('roiError').textContent=e.message}finally{this.busy=false;this.el('roiRun').disabled=false;this.el('roiClose').disabled=false}}
}

