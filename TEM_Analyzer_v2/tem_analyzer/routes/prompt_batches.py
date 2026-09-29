"""Image-scoped transfer inspection/confirmation; preparation is a batch job."""
import numpy as np
from PIL import Image,ImageDraw
from fastapi.responses import Response
from ..services.prompt_batches import current_transfer,transfer_signature,confirm_transfers
from ..preprocessing import exclusion_mask


def install(app,project):
    from ..v2_api import image_bytes

    @app.get('/api/workflow/prompt-transfers/{iid}')
    def transfer_info(iid:str):
        value=current_transfer(project,iid)
        return dict(value,signature=transfer_signature(value),reviewed=value.get('review_hash')==transfer_signature(value))

    @app.get('/api/workflow/prompt-transfers/{iid}/preview.png')
    def transfer_image(iid:str):
        value=current_transfer(project,iid);draft=value['draft'];rgb=project.image(iid)
        rgb[exclusion_mask(project,iid)]=rgb[exclusion_mask(project,iid)]//2+np.array([90,0,35],np.uint8)
        im=Image.fromarray(rgb);draw=ImageDraw.Draw(im);radius=max(2,round(min(rgb.shape[:2])*.006))
        for point in draft['auto_points']+draft['manual_points']:
            x,y=point[:2];color='cyan' if len(point)==2 else ('lime' if point[2] else 'red')
            draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color,outline='black')
        if draft['box'] is not None:draw.rectangle(draft['box'],outline='yellow',width=max(1,radius//2))
        return Response(image_bytes(np.asarray(im)),media_type='image/png')

    @app.post('/api/workflow/prompt-transfers/confirm')
    def confirm(body:dict):return confirm_transfers(project,body.get('entries',[]))
