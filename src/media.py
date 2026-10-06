"""Local audio analysis, word filtering, subtitles and rendered exports."""
import json,math,os,re,shutil,subprocess,tempfile,urllib.request,uuid
from pathlib import Path
import numpy as np
import core
from paths import BIN,BASE,DATA
FLAGS=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0

def exe(name):
    p=BIN/(name+('.exe' if os.name=='nt' else ''))
    if os.name!='nt' and not p.exists() and shutil.which(name):return shutil.which(name)
    if not p.exists():raise RuntimeError('Support asset missing: '+str(p)+'. Restart SceneSieve to repair setup.')
    return str(p)
def run(args,cancel=None,progress=None):
    with tempfile.TemporaryFile() as log:
        p=subprocess.Popen(args,stdout=log,stderr=log,creationflags=FLAGS)
        try:
            while True:
                try:code=p.wait(timeout=.2);break
                except subprocess.TimeoutExpired:
                    if cancel is not None and cancel.is_set():raise InterruptedError('Operation cancelled; existing output was preserved.')
            if code:
                log.seek(0);raise RuntimeError(log.read().decode(errors='replace')[-2500:])
        finally:
            if p.poll() is None:p.terminate();p.wait()
def probe(video):
    r=subprocess.run([exe('ffprobe'),'-v','error','-show_streams','-of','json',str(video)],capture_output=True,creationflags=FLAGS,timeout=30)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
    return json.loads(r.stdout)['streams']
def waveform(video,progress,cancel):
    stat=Path(video).stat();key=__import__('hashlib').sha256((str(Path(video).resolve())+str(stat.st_size)+str(stat.st_mtime_ns)).encode()).hexdigest();cache=DATA/'waveforms'/(key+'.json')
    try:return json.loads(cache.read_text())
    except (OSError,ValueError):pass
    if not any(s['codec_type']=='audio' for s in probe(video)):return {'step':.05,'peak':[],'rms':[]}
    peaks=[];rms=[];step=.05;rate=8000;block=int(rate*step)*4
    with tempfile.TemporaryFile() as log:
        p=subprocess.Popen([exe('ffmpeg'),'-v','error','-i',str(video),'-map','0:a:0','-vn','-ac','1','-ar',str(rate),'-f','f32le','pipe:1'],stdout=subprocess.PIPE,stderr=log,creationflags=FLAGS)
        try:
            while True:
                if cancel.is_set():raise InterruptedError('Audio analysis cancelled.')
                raw=p.stdout.read(block)
                if not raw:break
                a=np.frombuffer(raw[:len(raw)//4*4],dtype='<f4')
                peaks.append(float(np.max(np.abs(a))));rms.append(float(np.sqrt(np.mean(a*a))))
                if len(peaks)%20==0:progress(f'Analysing audio: {len(peaks)*step:.0f}s')
            if p.wait():log.seek(0);raise RuntimeError(log.read().decode(errors='replace')[-1000:])
        finally:
            if p.poll() is None:p.terminate();p.wait()
    data={'step':step,'peak':peaks,'rms':rms};cache.parent.mkdir(parents=True,exist_ok=True);core.atomic_text(cache,json.dumps(data));return data
def level_scenes(wave,duration,low=-40,high=-8,target=-20,min_duration=.3):
    data=np.asarray(wave['rms']);db=20*np.log10(np.maximum(data,1e-8));out=[]
    for label,mask in [('quiet audio',(db<low)&(db>-65)),('loud audio',db>high)]:
        start=None
        for i,hit in enumerate([*mask,False]):
            if hit and start is None:start=i
            if not hit and start is not None:
                a=start*wave['step'];b=min(duration,i*wave['step'])
                if b-a>=min_duration:
                    gain=max(-36,min(12,target-float(np.mean(db[start:i]))))
                    out.append(dict(start=a,end=b,category=label,action='gain',gain_db=gain,enabled=True,reviewed=False,source='audio-level'))
                start=None
    return out

def read_subtitles(path,duration):
    import pysubs2
    subs=pysubs2.load(str(path),encoding='utf-8-sig');out=[]
    for cue in subs:
        a=max(0,cue.start/1000);b=min(duration,cue.end/1000)
        if b>a:out.append({'start':a,'end':b,'text':cue.plaintext.replace('\n',' '),'precision':'cue'})
    return out

def transcribe(video,model,progress,cancel):
    from faster_whisper import WhisperModel
    os.environ['HF_HOME']=str(BASE/'models'/'speech')
    progress('Loading/downloading speech model '+model+' (first use may take several minutes)...')
    engine=WhisperModel(model,device='cpu',compute_type='int8',download_root=str(BASE/'models'/'speech'))
    segments,info=engine.transcribe(str(video),word_timestamps=True,vad_filter=True)
    progress('Transcribing audio: 0s')
    out=[]
    for segment in segments:
        if cancel.is_set():raise InterruptedError('Transcription cancelled.')
        for w in segment.words or []:
            if w.end>w.start:out.append({'start':w.start,'end':w.end,'text':w.word.strip(),'precision':'word'})
        progress(f'Transcribing audio: {segment.end:.1f}s')
    return out

def word_scenes(cues,terms,duration,amount):
    terms=[t.strip() for t in terms.split(',') if t.strip()]
    if not terms:raise ValueError('Enter one or more comma-separated words or phrases.')
    pattern=re.compile(r'(?<!\w)(?:'+ '|'.join(re.escape(t) for t in sorted(terms,key=len,reverse=True))+r')(?!\w)',re.I)
    # Search a unified transcript, preserving each token/cue time interval.
    spans=[];text=''
    for i,c in enumerate(cues):
        if text:text+=' '
        a=len(text);text+=c['text'];spans.append((a,len(text),i))
    out=[]
    for match in pattern.finditer(text):
        ids=[i for a,b,i in spans if a<match.end() and b>match.start()]
        if not ids:continue
        a=max(0,cues[ids[0]]['start']);b=min(duration,cues[ids[-1]]['end'])
        if b>a:out.append(dict(start=a,end=b,category='spoken word',action='duck',level=amount/100,enabled=True,reviewed=False,source='speech-search',text=match.group(),cue_ids=ids,precision='word' if all(cues[i].get('precision')=='word' for i in ids) else 'cue',redactions={str(i):[max(0,match.start()-x),min(y-x,match.end()-x)] for x,y,i in spans if i in ids}))
    return out

def audio_scenes(doc):return [s for s in doc['scenes'] if s['enabled'] and s.get('action') in ('duck','gain','bleep','replace','distort')]
def audio_filter(doc,start=0,normalize=False,replacement_start=None):
    filters=[]
    if normalize:filters.append('dynaudnorm=f=250:g=15:p=0.9:m=4')
    # Gains before limiter; word attenuation last so normalization cannot undo it.
    for s in audio_scenes(doc):
        if s['action']=='gain':filters.append(f"volume={10**(s.get('gain_db',0)/20):.8f}:enable='between(t,{s['start']-start:.6f},{s['end']-start:.6f})'")
    if filters:filters.append('alimiter=limit=0.95:level=false:latency=true')
    for s in audio_scenes(doc):
        if s['action'] in ('bleep','replace') and s.get('_mute_end',s['end'])>s['start']:filters.append(f"volume=0:enable='between(t,{s['start']-start:.6f},{s.get('_mute_end',s['end'])-start:.6f})'")
        if s['action']=='duck':filters.append(f"volume={s.get('level',0):.8f}:enable='between(t,{s['start']-start:.6f},{s['end']-start:.6f})'")
    for s in audio_scenes(doc):
        if s['action']=='distort':
            # Sample-accurate noise modulation keeps the amplitude envelope, but
            # discards the waveform carrying recognizable pitch and speech.
            filters.append(f"aeval=exprs='if(between(t,{s['start']-start:.6f},{s['end']-start:.6f}),abs(val(ch))*(2*random(0)-1),val(ch))':c=same")
    import replacements
    return replacements.graph(doc,start if replacement_start is None else replacement_start,','.join(filters) or 'anull')

def subtitle_text(doc,kept):
    cues=doc.get('subtitles',[]);blocked=[s for s in audio_scenes(doc) if s['action'] in ('duck','bleep','replace','distort')];events=[];offset=0.
    for a,b in kept:
        for cue_index,c in enumerate(cues):
            x,y=max(a,c['start']),min(b,c['end'])
            if y<=x:continue
            text=c['text'];edits=[]
            for s in blocked:
                if s['start']<c['end'] and s['end']>c['start']:
                    if str(cue_index) in s.get('redactions',{}):
                        replacement=s.get('replacement','') if s['action']=='replace' and cue_index==min(map(int,s['redactions'])) else ''
                        edits.append([*s['redactions'][str(cue_index)],replacement]);continue
                    term=s.get('text','')
                    if term:text=re.sub(r'(?<!\w)'+re.escape(term)+r'(?!\w)',lambda _:s.get('replacement','') if s['action']=='replace' else '',text,flags=re.I)
                    if c.get('precision')=='word' and (not term or text==c['text']):text=s.get('replacement','') if s['action']=='replace' else ''
            for lo,hi,replacement in sorted(edits,reverse=True):text=text[:lo]+replacement+text[hi:]
            text=' '.join(text.split())
            if not text:continue
            events.append([offset+x-a,offset+y-a,text,c.get('precision','cue')])
        offset+=b-a
    grouped=[]
    for a,b,text,precision in sorted(events,key=lambda e:e[0]):
        if grouped and precision=='word' and grouped[-1][3]=='word' and a-grouped[-1][1]<=.4 and b-grouped[-1][0]<=5 and len(grouped[-1][2])+len(text)<80:
            grouped[-1][1]=b;grouped[-1][2]+=' '+text
        else:grouped.append([a,b,text,precision])
    return '\n'.join(f'{i}\n{core.clock(a).replace(".",",")} --> {core.clock(b).replace(".",",")}\n{text}\n' for i,(a,b,text,_) in enumerate(grouped,1))

def display_subtitles(doc):
    if not doc.get('subtitles'):return []
    if not any(s.get('action') in ('duck','bleep','replace','distort') for s in audio_scenes(doc)):return doc['subtitles']
    import pysubs2
    text=subtitle_text(doc,[(0,doc['duration'])])
    return [dict(start=c.start/1000,end=c.end/1000,text=c.plaintext,precision='cue') for c in pysubs2.SSAFile.from_string(text,format_='srt')] if text.strip() else []

def export_media(video,doc,destination,categories,padding,normalize,progress,cancel,audio_only=False,lossless_audio=False):
    dest=Path(destination)
    if dest.resolve()==Path(video).resolve():raise ValueError('Export must not overwrite the source video.')
    kept=core.kept_ranges(doc['duration'],core.cuts(doc,categories,padding))
    if doc.get('_preview_range'):
        lo,hi=doc['_preview_range'];kept=[(max(a,lo),min(b,hi)) for a,b in kept if max(a,lo)<min(b,hi)]
    if not kept:raise ValueError('All video is excluded.')
    streams=probe(video);has_audio=any(s['codec_type']=='audio' for s in streams)
    if audio_only and not has_audio:raise ValueError('This media has no audio track.')
    with tempfile.TemporaryDirectory(prefix='scenesieve-export-',dir=dest.parent) as folder:
        folder=Path(folder);parts=[]
        import visual_effects
        plan=[(a,b,None) for a,b in kept] if audio_only else visual_effects.segments(doc,kept,categories,padding)
        video_stream=next((s for s in streams if s['codec_type']=='video'),{})
        for i,(a,b,effect) in enumerate(plan):
            progress(f'Rendering segment {i+1}/{len(plan)} ({a:.1f}–{b:.1f}s)...')
            part=folder/f'{i:06d}.mkv';parts.append(part)
            cmd=[exe('ffmpeg'),'-v','error','-nostdin','-y','-ss',str(a),'-i',str(video),'-t',str(b-a)]
            if not audio_only:
                vf='null';video_input='0:v:0'
                if effect and effect['action']=='freeze':
                    # Hold a frame before the protected interval; at time zero
                    # there is no preceding safe frame, so hold black instead.
                    rate=video_stream.get('avg_frame_rate','25/1')
                    num,den=map(float,rate.split('/'));fps=num/den if den and num else 25
                    anchor=max(0,effect['start']-2/fps)
                    cmd=cmd[:-2]+['-ss',str(anchor),'-i',str(video),'-t',str(b-a)]
                    video_input='1:v:0'
                    vf=f'trim=end_frame=1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={b-a},trim=duration={b-a}'
                    if effect['start']==0:vf+=',drawbox=color=black:t=fill'
                elif effect:
                    vf=visual_effects.spatial_filter(effect['action'],video_stream['width'],video_stream['height'])
                cmd+=['-map',video_input,'-vf',vf,'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p']
            if has_audio:cmd+=['-map','0:a:0','-af',audio_filter(doc,a,normalize),'-c:a','flac','-ar','48000']
            cmd+=['-sn',str(part)];run(cmd,cancel)
        listing=folder/'concat.txt';listing.write_text('\n'.join("file '"+p.name+"'" for p in parts))
        output=folder/('result'+dest.suffix);cmd=[exe('ffmpeg'),'-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(listing)]
        srt=subtitle_text(doc,kept);subfile=folder/'filtered.srt'
        if srt and not audio_only:subfile.write_text(srt,encoding='utf-8');cmd+=['-i',str(subfile)]
        if not audio_only:cmd+=['-map','0:v:0','-c:v','copy']
        if has_audio:
            codec='pcm_s16le' if dest.suffix.lower()=='.wav' else 'flac' if lossless_audio or dest.suffix.lower()=='.flac' else 'aac'
            cmd+=['-map','0:a:0','-c:a',codec]
            if codec=='aac':cmd+=['-b:a','192k']
        if srt and not audio_only:cmd+=['-map','1:0','-c:s','srt' if dest.suffix.lower()=='.mkv' else 'mov_text']
        cmd+=[str(output)];progress('Assembling filtered output...');run(cmd,cancel)
        os.replace(output,dest)
    if srt:core.atomic_text(dest.with_suffix('.filtered.srt'),srt)
    return str(dest)

def embedded_subtitles(video,index,progress,cancel,duration):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'sub.srt';run([exe('ffmpeg'),'-v','error','-nostdin','-i',str(video),'-map',f'0:{index}',str(p)],cancel)
        return read_subtitles(p,duration)

def download_subtitles(url,duration):
    if not url.lower().startswith('https://'):raise ValueError('Use an HTTPS link to an SRT, VTT or ASS subtitle file.')
    with urllib.request.urlopen(url,timeout=30) as r:
        if not r.url.lower().startswith('https://'):raise ValueError('Subtitle download redirected to an insecure address.')
        data=r.read(10*1024*1024+1)
    if len(data)>10*1024*1024:raise ValueError('Subtitle file exceeds 10 MB.')
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'download.srt';p.write_bytes(data);return read_subtitles(p,duration)
