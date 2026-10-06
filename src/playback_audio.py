"""Incremental filtered playback: original spans plus cached affected clips."""
import hashlib,json,math,os
from pathlib import Path
import core,media,visual_effects,replacements

AUDIO_FIELDS=('action','start','end','level','gain_db','replacement','voice','frequency','replacement_level')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def identity(video):
    source=Path(video);stat=source.stat()
    return [str(source.resolve()),stat.st_size,stat.st_mtime_ns]
def cache_path(folder,video,doc,categories,padding,video_effects=False):
    return Path(folder)/('playback-plan-'+digest([3,identity(video),doc,sorted(categories),padding])+'.edl')
def spans(doc,categories,padding,has_audio=True):
    kept=core.kept_ranges(doc['duration'],core.cuts(doc,categories,padding))
    if doc.get('_preview_range'):
        lo,hi=doc['_preview_range'];kept=[(max(a,lo),min(b,hi)) for a,b in kept if max(a,lo)<min(b,hi)]
    audio=media.audio_scenes(doc) if has_audio else []
    ends={id(s):max(s['end'],s['start']+replacements.duration(s)) if s['action']=='replace' else s['end'] for s in audio}
    for a,b,effect in visual_effects.segments(doc,kept,categories,padding):
        points={a,b}
        for s in audio:
            points.update(t for t in (s['start'],ends[id(s)]) if a<t<b)
        points.update(t for t in range((math.floor(a/10)+1)*10,math.ceil(b/10)*10,10) if a<t<b)
        points=sorted(points)
        for x,y in zip(points,points[1:]):
            treatments=[s for s in audio if s['start']<y and ends[id(s)]>x]
            yield x,y,effect,treatments

def prepare(path,video,doc,categories,padding,progress,cancel,video_effects=False):
    path=Path(path);folder=path.parent/'preview-segments';folder.mkdir(exist_ok=True)
    source_id=identity(video)
    has_audio=any(s['codec_type']=='audio' for s in media.probe(video))
    plan=list(spans(doc,categories,padding,has_audio))
    if not plan:raise ValueError('This preview is entirely skipped.')
    entries=[]
    # Dynamic normalization uses temporal context. Keep its continuous render
    # instead of introducing gain discontinuities at cache boundaries.
    if doc.get('normalize_audio') and has_audio:
        render_doc={**doc,'subtitles':[],'scenes':[{**{k:s[k] for k in (*AUDIO_FIELDS,'category','enabled') if k in s},'reviewed':True} for s in doc['scenes']]}
        render_doc={k:v for k,v in render_doc.items() if k in ('version','duration','scenes','_preview_range')}
        clip=folder/(digest([2,source_id,render_doc,sorted(categories),padding,'normalize'])+'.mkv')
        if not clip.exists():media.export_media(video,render_doc,clip,categories,padding,True,progress,cancel,lossless_audio=True)
        else:progress('Reusing normalized preview...')
        entries=[(clip,0,sum(b-a for a,b,_,_ in plan))]
    else:
        for i,(a,b,effect,audio) in enumerate(plan):
            if cancel is not None and cancel.is_set():raise InterruptedError('Preview preparation cancelled.')
            if not effect and not audio:
                if entries and entries[-1][0]==video and entries[-1][2]==a:entries[-1]=(video,entries[-1][1],b)
                else:entries.append((video,a,b))
                continue
            scenes=[]
            if effect:scenes.append(dict(start=effect['start'],end=effect['end'],action=effect['action'],category='effect',enabled=True,reviewed=True))
            scenes.extend({**{k:s[k] for k in AUDIO_FIELDS if k in s},'category':'audio','enabled':True,'reviewed':True} for s in audio)
            clip_doc=dict(version=1,duration=doc['duration'],scenes=scenes,_preview_range=[a,b])
            clip=folder/(digest([2,source_id,clip_doc])+'.mkv')
            if not clip.exists():
                progress(f'Rendering segment {i+1}/{len(plan)} ({a:.1f}-{b:.1f}s)...')
                media.export_media(video,clip_doc,clip,None,0,False,lambda _:None,cancel,lossless_audio=True)
            else:progress(f'Reusing cached segment {i+1}/{len(plan)} ({a:.1f}-{b:.1f}s)')
            entries.append((clip,0,b-a))
    text='# mpv EDL v0\n'+''.join(core._mpv_ranges(p,[(a,b)]).split('\n',1)[1] for p,a,b in entries)
    core.atomic_text(path,text);progress('Filtered preview ready; unchanged footage uses the original media.')
    return str(path)
