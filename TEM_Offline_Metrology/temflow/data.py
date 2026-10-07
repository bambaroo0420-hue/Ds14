"""Company image / semantic-GT ingestion. Never silently quantize annotation colors."""
from pathlib import Path
import json, hashlib
import numpy as np
from PIL import Image
from .core import read_image, digest


def upload_widget(folder):
    import ipywidgets as widgets
    from IPython.display import display
    import html
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    upload=widgets.FileUpload(accept='.png,.tif,.tiff,.jpg,.jpeg',multiple=True)
    button=widgets.Button(description='Save uploads');out=widgets.HTML()
    selected=widgets.Dropdown(description='Image:',layout=widgets.Layout(width='95%'))
    def refresh(preferred=None):
        paths=sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.png','.tif','.tiff','.jpg','.jpeg'))
        old=selected.value
        selected.options=[(p.name,str(p)) for p in paths]
        if preferred in [str(p) for p in paths]:selected.value=preferred
        elif old in [str(p) for p in paths]:selected.value=old
    def save(_):
        try:
            raw=upload.value
            values=list(raw.items()) if isinstance(raw,dict) else [(None,v) for v in raw]
            if not values:
                refresh();out.value='No new upload received. Choose Upload or select an existing image below.';return
            messages=[];last=None
            for key,v in values:
                name=Path(v.get('name') or v.get('metadata',{}).get('name') or key).name
                content=bytes(v['content'])
                if not content:raise ValueError('Empty upload: '+name)
                destination=folder/name
                if destination.exists() and destination.read_bytes()!=content:
                    destination=folder/(Path(name).stem+'_'+hashlib.sha256(content).hexdigest()[:12]+Path(name).suffix)
                if destination.exists() and destination.read_bytes()!=content:raise ValueError('Conflicting filename: '+destination.name)
                destination.write_bytes(content);last=str(destination)
                messages.append('Saved: '+destination.name+' ('+str(len(content))+' bytes)')
            refresh(last);out.value='<br>'.join(html.escape(s) for s in messages)
        except Exception as exc:out.value='<b>Upload failed:</b> '+html.escape(str(exc))
    upload.selected_path=selected
    upload.observe(save,names='value')
    button.on_click(save);refresh();display(widgets.VBox([upload,button,out,selected]))
    return upload


def inspect_gt(mask_dir):
    values=set();colors=set();types=set()
    for path in sorted(Path(mask_dir).glob('*')):
        if not path.is_file():continue
        a=np.asarray(Image.open(path))
        if a.ndim==2: types.add('indexed');values.update(map(int,np.unique(a)))
        elif a.ndim==3 and a.shape[2] in (3,4):
            types.add('rgb')
            if a.shape[2]==4 and (a[:,:,3]!=255).any():raise ValueError('Transparent GT: explicitly convert transparency to ignore before use')
            c=np.unique(a[:,:,:3].reshape(-1,3),axis=0)
            if len(c)>256:raise ValueError(f'{path.name}: >256 colors; lossy/antialiased GT must be corrected, not silently quantized')
            colors.update(map(tuple,c.tolist()))
        else: raise ValueError('Unsupported GT format: '+str(path))
    report=dict(types=sorted(types),indexed_values=sorted(values),rgb_colors=[list(c) for c in sorted(colors)])
    print(json.dumps(report,indent=2));return report


def propose_rgb_map(report):
    """Exact-color proposal, requiring human class interpretation; no color quantization."""
    mapping={};next_id=1
    for color in report['rgb_colors']:
        if color==[0,0,0]:value=0
        else:value=next_id;next_id+=1
        mapping[','.join(map(str,color))]=value
    print('Proposed IDs (review background/ignore/material names):',mapping)
    return mapping or None


def decode_gt(path,rgb_map=None,id_map=None):
    a=np.asarray(Image.open(path))
    if a.ndim==3:
        if rgb_map is None:raise ValueError('Supply explicit RGB-to-class mapping after inspection')
        out=np.full(a.shape[:2],-1,np.int32)
        for color,c in rgb_map.items():
            key=tuple(map(int,color.split(',')))
            out[(a[:,:,:3]==key).all(2)]=int(c)
        if (out<0).any():raise ValueError('Unmapped GT color in '+str(path))
        a=out
    else:
        a=a.astype(np.int32)
        if id_map is not None:
            out=np.full_like(a,-1)
            for old,new in id_map.items():out[a==int(old)]=int(new)
            if (out<0).any():raise ValueError('Unmapped GT class ID')
            a=out
    if ((a<0)|(a>65535)).any():raise ValueError('GT labels must be nonnegative integer IDs')
    return a


def prepare_dataset(root, rgb_map=None, id_map=None, groups=None, val_fraction=.2, seed=42, ignore=255):
    root=Path(root);groups=groups or {};raw=root/'data/images';masks=root/'data/gt'
    normalized=root/'data/gt_ids';normalized.mkdir(parents=True,exist_ok=True)
    files=[p for p in sorted(raw.glob('*')) if p.suffix.lower() in ['.png','.tif','.tiff','.jpg','.jpeg']]
    if len({p.stem for p in files})!=len(files):raise ValueError('Duplicate image stems')
    gts=[p for p in masks.glob('*') if p.is_file()]
    if len({p.stem for p in gts})!=len(gts):raise ValueError('Duplicate GT stems')
    lookup={p.stem:p for p in gts};rows=[];hashes={}
    for p in files:
        if p.stem not in lookup:raise ValueError('Missing GT for '+p.name)
        image=read_image(p);a=decode_gt(lookup[p.stem],rgb_map,id_map)
        if a.shape!=image.shape[:2]:raise ValueError('Image/GT shape mismatch: '+p.name)
        pixelhash=hashlib.sha256(image.tobytes()).hexdigest();group=groups.get(p.stem,p.stem)
        if pixelhash in hashes and hashes[pixelhash]!=group:raise ValueError('Identical pixels occur in different groups')
        hashes[pixelhash]=group
        dest=normalized/(p.stem+'.png');Image.fromarray(a.astype('uint16')).save(dest)
        rows.append(dict(id=p.stem,image=p.relative_to(root).as_posix(),gt=dest.relative_to(root).as_posix(),group=group,
                         image_sha256=digest(p),gt_sha256=digest(dest),pixel_sha256=pixelhash,
                         classes=[int(c) for c in np.unique(a) if c!=ignore]))
    if not rows:raise ValueError('Upload original images and GT first')
    allgroups=sorted({r['group'] for r in rows})
    if len(allgroups)<2:raise ValueError('At least two independent groups are needed for train/validation. Do not split crops of one image.')
    manifest=root/'data/manifest.json'
    if manifest.exists():
        old=json.loads(manifest.read_text())
        signature=lambda z:{(r['id'],r['image_sha256'],r['gt_sha256'],r['group']) for r in z}
        if signature(old)!=signature(rows):raise ValueError('Data changed. Archive the previous manifest before rebuilding a split.')
        rows=old
    else:
        rng=np.random.default_rng(seed);rng.shuffle(allgroups);n=max(1,min(len(allgroups)-1,round(len(allgroups)*val_fraction)))
        valid=set(allgroups[:n])
        for r in rows:r['split']='val' if r['group'] in valid else 'train'
        manifest.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    print('train:',sum(r['split']=='train' for r in rows),'val:',sum(r['split']=='val' for r in rows))
    return rows


def preview_dataset(root, rows, count=6):
    import matplotlib.pyplot as plt
    root=Path(root);fig,axs=plt.subplots(min(count,len(rows)),2,figsize=(10,3*min(count,len(rows))),squeeze=False)
    for ax,r in zip(axs,rows):
        ax[0].imshow(read_image(root/r['image']));ax[1].imshow(np.asarray(Image.open(root/r['gt'])),interpolation='nearest')
        ax[0].set_title(f"{r['id']} / group={r['group']} / {r['split']}");ax[1].set_title('Class IDs '+str(r['classes']))
    return fig
