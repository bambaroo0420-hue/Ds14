import io,json,zipfile
import numpy as np
from PIL import Image
from core import Document,normal_dp,semantic_edges,recognize

def test_peak_can_move_without_initial_distance_penalty():
    im=np.zeros((60,80)); im[30:]=200
    p=[[5,24],[74,24]]
    for continuity in (0,.2):
        out=normal_dp(im,p,width=10,continuity=continuity,sigma=1)
        ys=np.array(out['points'])[:,1]
        assert np.max(np.abs(ys-29.5))<=.6

def test_diagonal_normals_move_to_edge():
    y,x=np.mgrid[:90,:90]; im=(y>=x+6)*200.
    out=normal_dp(im,[[10,12],[65,67]],width=8,continuity=.1,sigma=1)
    p=np.array(out['points']); assert np.mean(np.abs(p[:,1]-p[:,0]-5.5))<1.2

def test_closed_dp_closes():
    y,x=np.mgrid[:64,:64]; im=((x-32)**2+(y-32)**2<20**2)*200.
    t=np.linspace(0,2*np.pi,70,endpoint=False)
    p=np.column_stack([32+16*np.cos(t),32+16*np.sin(t)])
    out=normal_dp(im,p,width=7,continuity=.1,closed=True)
    q=np.array(out['points']); r=np.linalg.norm(q-[32,32],axis=1)
    assert np.mean(np.abs(r-20))<1
    assert np.linalg.norm(q[0]-q[-1])<3

def test_ignore_is_not_background_edge():
    a=np.ones((30,30),np.uint16); valid=np.ones((30,30),bool);valid[:,20:]=False
    e,v=semantic_edges(a,valid);assert not e.any();assert not v[:,20:].any()

def test_edge_band_three_pixels():
    a=np.ones((25,25),np.uint16);a[12:]=2
    e,v=semantic_edges(a,np.ones_like(a,bool))
    assert e[:,12].sum()==3

def test_project_and_export_roundtrip():
    d=Document(Image.new('RGB',(40,30)),'specimen')
    d.labels[:15]=1;d.labels[15:]=2;d.valid[:]=True;d.exclude[:4,:]=True
    d.meta['scale']={'nm_per_pixel':.32,'confirmed':True}
    d2=Document.load(d.project());assert np.array_equal(d.labels,d2.labels);assert np.array_equal(d.exclude,d2.exclude)
    with zipfile.ZipFile(io.BytesIO(d2.export())) as z:
        sem=np.asarray(Image.open(io.BytesIO(z.read('semantic_gt/specimen.png'))))
        ed=np.asarray(Image.open(io.BytesIO(z.read('edge_gt/specimen.png'))))
        valid=np.asarray(Image.open(io.BytesIO(z.read('valid_semantic/specimen.png'))))
        assert sem.shape==ed.shape==valid.shape==(30,40);assert not valid[:4].any()
        assert set(np.unique(ed))<={0,1}
        assert json.loads(z.read('metadata/specimen.json'))['scale']['nm_per_pixel']==.32

def test_superpixel_edit_undo():
    d=Document(Image.fromarray(np.tile(np.arange(80,dtype=np.uint8),(60,1))))
    d.superpixels([10,10,70,50],size=8);assert not d.sp[:10].any()
    m=d.sp==d.sp[20,20];d.edit(m,2);assert (d.labels[m]==2).all()
    d.undo();assert not d.valid.any();d.undo(True);assert d.valid.any()

def test_polyline_semantic_consistency():
    im=np.zeros((60,80),np.uint8);im[30:]=200
    d=Document(Image.fromarray(im));d.refine(cid=1,line=[[0,25],[79,25]],roi=[0,0,80,60],width=8,continuity=.1,sigma=1)
    d.accept(other=2)
    assert (d.labels[10,:]==2).all() and (d.labels[45,:]==1).all()
    assert d.valid.all()

def test_api_flow():
    import app as a
    client=a.app.test_client();h={'X-GT-Token':a.TOKEN}
    r=client.post('/api/demo',json={},headers=h);key=r.json['id']
    data={'id':key,'kind':'polygon','points':[[20,20],[200,20],[200,100],[20,100]],'cid':1}
    assert client.post('/api/edit',json=data,headers=h).status_code==200
    assert client.get('/api/export?id='+key).status_code==400
    assert client.post('/api/scale',json={'id':key,'points':[[10,10],[210,10]],'nm':50},headers=h).status_code==200
    assert client.post('/api/review',json={'id':key,'reviewed':True},headers=h).status_code==200
    r=client.get('/api/export?id='+key);assert r.status_code==200
    assert zipfile.is_zipfile(io.BytesIO(r.data))
    assert client.post('/api/delete',json={'id':key},headers=h).status_code==200

def test_ocr_scale_and_manual_exclusion(monkeypatch):
    import ocr_adapter
    monkeypatch.setattr(ocr_adapter,"read_words",lambda *args,**kw:[
        {"text":"120k","box":[482,14,529,29],"confidence":96},
        {"text":"50 nm","box":[71,347,132,362],"confidence":81},
        {"text":"Sample A-01","box":[351,334,476,353],"confidence":92}])
    import app as a
    client=a.app.test_client();h={'X-GT-Token':a.TOKEN}
    key=client.post('/api/demo',json={},headers=h).json['id']
    r=client.post('/api/ocr',json={'id':key},headers=h)
    assert r.status_code==200
    assert any(w['text']=='120k' for w in r.json['words'])
    best=r.json['candidates'][0]; assert best['nm_per_pixel']==.25
    r=client.post('/api/scale',json={'id':key,'points':best['points'],'nm':50,'bar_box':best['box']},headers=h)
    assert r.status_code==200
    r=client.post('/api/exclude_ocr',json={'id':key},headers=h); assert r.status_code==200
    d=a.DOCS[key]; assert d.exclude[330,100]
    assert d.exclude[20,500]

def test_empty_ocr_exclusion_and_manual_scale():
    import app as a
    client=a.app.test_client();h={'X-GT-Token':a.TOKEN}
    key=client.post('/api/demo',json={},headers=h).json['id']
    assert client.post('/api/exclude_ocr',json={'id':key},headers=h).status_code==200
    r=client.post('/api/scale',json={'id':key,'points':[[2.1,10.2],[202.1,10.2]],'nm':50,'bar_box':[2.1,8.2,202.1,12.2]},headers=h)
    assert r.status_code==200
    assert client.post('/api/exclude_ocr',json={'id':key},headers=h).status_code==200

def test_frontend_ids_and_local_assets():
    import re
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text();js=(root/'static/app.js').read_text()
    ids=set(re.findall(r'id="([^"]+)"',html))
    refs=set(re.findall(r"\$\('([^']+)'\)",js))
    assert refs<=ids
    assert 'https://' not in html

def test_canonical_center_matches_edge():
    from core import semantic_center
    from scipy.ndimage import binary_dilation,generate_binary_structure
    d=Document(Image.new('RGB',(30,30)));d.valid[:]=True;d.labels[:15]=1;d.labels[15:]=2
    with zipfile.ZipFile(io.BytesIO(d.export())) as z:
        center=np.asarray(Image.open(io.BytesIO(z.read('boundary_center/image.png'))))
        edge=np.asarray(Image.open(io.BytesIO(z.read('edge_gt/image.png'))))
        ev=np.asarray(Image.open(io.BytesIO(z.read('valid_edge/image.png'))))
        assert np.array_equal(edge,binary_dilation(center,structure=generate_binary_structure(2,1))&ev.astype(bool))
