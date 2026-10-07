"""Nested image-count plans. Validation/test untouched; class coverage explicit."""
import random

def plan_image_counts(rows, samples, classes, seed=42):
    train=sorted((r for r in rows if r['split']=='train'),key=lambda r:r['id'])
    if not train:raise ValueError('No train images')
    if not any(r['split']=='test' for r in rows):raise ValueError('Independent test required')
    coverage={r['id']:{s['cls'] for s in samples if s['row']['id']==r['id']} for r in train}
    empty=[id for id,c in coverage.items() if not c]
    if empty:raise ValueError('Train images without usable target masks: '+str(empty))
    # Cover each selected class first; shuffle remaining images with fixed seed.
    pool=train.copy();random.Random(seed).shuffle(pool);order=[];remaining=set(classes)
    while remaining:
        if not pool:raise ValueError('Selected class absent from training')
        chosen=max(pool,key=lambda r:len(coverage[r['id']]&remaining))
        if not coverage[chosen['id']]&remaining:raise ValueError('Selected class absent from training')
        order.append(chosen);pool.remove(chosen);remaining-=coverage[chosen['id']]
    required=len(order);order.extend(pool)
    plan=[dict(label='0',count=0,rows=rows,train_ids=[],baseline=True)]
    skipped=[];fixed=[r for r in rows if r['split']!='train']
    for n in (5,10):
        if len(train)<n:skipped.append(f'{n}: only {len(train)} train images');continue
        if n<required:skipped.append(f'{n}: class coverage requires {required} images');continue
        selected=order[:n]
        plan.append(dict(label=str(n),count=n,rows=selected+fixed,train_ids=[r['id'] for r in selected],baseline=False))
    # Keep the ALL label even if it matches 5 or 10; notebook reuses that result.
    plan.append(dict(label='all',count=len(train),rows=order+fixed,train_ids=[r['id'] for r in order],baseline=False))
    return plan,skipped
