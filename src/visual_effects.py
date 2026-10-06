"""Source-time visual treatments shared by export and filtered playback."""
OPTIONS=(('Skip','skip'),('Pixelate','pixelate'),('Blur','blur'),('More blur','blur_strong'),('Freeze frame','freeze'))
LABELS={value:label for label,value in OPTIONS}
ACTIONS=tuple(value for _,value in OPTIONS[1:])

def scenes(doc,categories=None,padding=0):
    return [{**s,'start':max(0,s['start']-padding),'end':min(doc['duration'],s['end']+padding)}
            for s in doc['scenes'] if s['enabled'] and s.get('action') in ACTIONS
            and (categories is None or s['category'] in categories)]

def segments(doc,kept,categories=None,padding=0):
    effects=scenes(doc,categories,padding);out=[]
    priority={'blur':1,'blur_strong':2,'pixelate':3,'freeze':4}
    for a,b in kept:
        boundaries=sorted({a,b,*[t for s in effects for t in (s['start'],s['end']) if a<t<b]})
        for x,y in zip(boundaries,boundaries[1:]):
            active=[s for s in effects if s['start']<y and s['end']>x]
            effect=max(active,key=lambda s:(priority[s['action']],-s['start'])) if active else None
            out.append((x,y,effect))
    return out

def spatial_filter(action,width,height):
    if action=='pixelate':
        return f'scale={max(2,width//48)}:{max(2,height//48)}:flags=area,scale={width}:{height}:flags=neighbor'
    if action in ('blur','blur_strong'):
        sigma=max(8,min(width,height)*(0.025 if action=='blur' else 0.09))
        return f'gblur=sigma={sigma:.3f}:steps=3'
    return 'null'
