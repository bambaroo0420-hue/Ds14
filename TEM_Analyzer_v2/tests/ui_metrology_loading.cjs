// Small mocked loading contract; actual decoded browser screenshots are separate.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const images=[];
class Image{
 constructor(){this.naturalWidth=100;this.naturalHeight=80;images.push(this)}
 decode(){return Promise.resolve()}
 removeAttribute(){this.src=''}
}
const context=vm.createContext({Image,setTimeout,clearTimeout,Promise,Error});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/modules/metrology.js'),'utf8').replace(/^import .*;\r?\n/gm,'').replaceAll('export function','function')+'\nthis.prepare=prepareComparisonImage;',context);
(async()=>{
 let done=false,p=context.prepare('ready.png','원본',1000).then(r=>{done=true;return r});
 await Promise.resolve();assert(!done);const first=images.at(-1);await first.onload();assert.equal((await p).src,'ready.png');assert(!first.onload&&!first.onerror);
 p=context.prepare('bad.png','원본',1000);let bad=images.at(-1);bad.onerror();await assert.rejects(p,/불러올/);assert.equal(bad.src,'');
 p=context.prepare('zero.png','원본',1000);bad=images.at(-1);bad.naturalWidth=0;await bad.onload();await assert.rejects(p,/디코딩/);
 p=context.prepare('decode.png','회전',1000);bad=images.at(-1);bad.decode=()=>Promise.reject(Error('invalid'));await bad.onload();await assert.rejects(p,/디코딩/);
 p=context.prepare('pending.png','회전',5);await assert.rejects(p,/시간 초과/);assert.equal(images.at(-1).src,'');
 p=context.prepare('slow-decode.png','회전',5);bad=images.at(-1);let finish;bad.decode=()=>new Promise(r=>finish=r);const handler=bad.onload;handler();await assert.rejects(p,/시간 초과/);finish();await Promise.resolve();assert.equal(bad.src,'');
 p=context.prepare('retry.png','회전',1000);await images.at(-1).onload();assert.equal((await p).src,'retry.png');
 console.log('PASS: comparison decode readiness, load failure, empty image, decode failure, request/decode timeout, late completion and retry');
})().catch(e=>{console.error(e);process.exitCode=1});
