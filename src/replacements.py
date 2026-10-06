"""Cached bleep and Windows system-voice replacements; no voice cloning."""
import hashlib,json,os,sys,subprocess,tempfile,wave
from pathlib import Path
import numpy as np
from paths import DATA

def prepare(scene):
    from media import run,exe,FLAGS
    duration=scene['end']-scene['start'];kind=scene['action']
    settings={'kind':kind,'duration':round(duration,6),'frequency':scene.get('frequency',1000),'replacement':scene.get('replacement','Darn!'),'level':scene.get('replacement_level',.15),'voice':scene.get('voice',''),'version':3}
    folder=DATA/'replacement-audio';folder.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest();dest=folder/(key+'.wav')
    if dest.exists():return dest
    rate=48000;count=max(1,round(duration*rate))
    if kind=='bleep':samples=np.sin(2*np.pi*settings['frequency']*np.arange(count)/rate)
    else:
        phrase=settings['replacement'].strip()
        if not phrase or len(phrase)>120:raise ValueError('Use a replacement phrase of 1–120 characters.')
        raw=folder/(hashlib.sha256((settings['voice']+'\0'+phrase).encode()).hexdigest()+'-voice.wav')
        if not raw.exists():
            with tempfile.TemporaryDirectory(dir=folder) as d:
                text=Path(d)/'text.txt';text.write_text(phrase,encoding='utf-8')
                target=Path(d)/'voice.wav'
                script="Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; try {if ($env:SCENESIEVE_TTS_VOICE) {$s.SelectVoice($env:SCENESIEVE_TTS_VOICE)}; $s.SetOutputToWaveFile($env:SCENESIEVE_TTS_OUTPUT); $s.Speak([IO.File]::ReadAllText($env:SCENESIEVE_TTS_TEXT))} finally {$s.Dispose()}"
                env=os.environ.copy();env.update(SCENESIEVE_TTS_OUTPUT=str(target),SCENESIEVE_TTS_TEXT=str(text),SCENESIEVE_TTS_VOICE=settings['voice'])
                if sys.platform=='darwin':
                    args=['/usr/bin/say','-f',str(text),'-o',str(target),'--file-format=WAVE','--data-format=LEI16@22050']
                    if settings['voice']:args+=['-v',settings['voice']]
                elif os.name!='nt':
                    args=['espeak-ng','-f',str(text),'-w',str(target)]
                    if settings['voice']:args+=['-v',settings['voice']]
                else:args=[str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-NonInteractive','-Command',script]
                r=subprocess.run(args,env=env,capture_output=True,creationflags=FLAGS,timeout=60)
                if r.returncode or not target.exists():raise RuntimeError('System speech synthesis failed. Choose Bleep or install a speech voice. '+r.stderr.decode(errors='replace')[-400:])
                os.replace(target,raw)
        with wave.open(str(raw),'rb') as w:spoken=w.getnframes()/w.getframerate()
        # Keep the natural system-voice duration; mix its tail over following audio.
        with tempfile.TemporaryDirectory(dir=folder) as d:
            fitted=Path(d)/'natural.wav'
            run([exe('ffmpeg'),'-v','error','-nostdin','-y','-i',str(raw),'-ar',str(rate),'-ac','1','-c:a','pcm_s16le',str(fitted)])
            with wave.open(str(fitted),'rb') as w:samples=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768
    peak=max(float(np.max(np.abs(samples))),1e-8);samples=samples/peak*settings['level']
    fade=min(round(.005*rate),len(samples)//2)
    if fade:samples[:fade]*=np.linspace(0,1,fade);samples[-fade:]*=np.linspace(1,0,fade)
    tmp=dest.with_suffix('.tmp')
    with wave.open(str(tmp),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes((samples*32767).astype('<i2').tobytes())
    os.replace(tmp,dest);return dest

def duration(scene,path=None):
    if scene.get('action')!='replace':return scene['end']-scene['start']
    path=path or prepare(scene)
    if not path.exists():return scene['end']-scene['start']
    with wave.open(str(path),'rb') as stream:return stream.getnframes()/stream.getframerate()

def prepare_all(scenes,progress=lambda _:None,cancel=None):
    for i,s in enumerate(scenes):
        if cancel is not None and cancel.is_set():raise InterruptedError('Replacement preparation cancelled.')
        if s.get('action') in ('bleep','replace') and s.get('enabled'):
            progress(f'Preparing replacement {i+1}/{len(scenes)}...');prepare(s)
    return scenes

def graph(doc,start,base):
    streams=[]
    occupied_end=float('-inf')
    for s in sorted(doc['scenes'],key=lambda s:(s['start'],s['end'])):
        if not s['enabled'] or s.get('action') not in ('bleep','replace'):continue
        # Mapped preview scenes preserve the original cached clip and crop offset.
        source=s.get('_replacement_source',s);path=prepare(source)
        finish=s.get('_replacement_end',s['start']+duration(source,path))
        begin=max(start,s['start']) if s['action']=='replace' else max(start,s['start'],occupied_end)
        if begin>=finish:continue
        offset=s.get('_replacement_offset',0)+begin-s['start']
        length=finish-begin;delay=begin-start
        if s['action']=='bleep':occupied_end=s['end']
        path_text=str(path.resolve()).replace('\\','/')
        option=''.join('\\'+c if c in "\\':" else c for c in path_text)
        escaped=''.join('\\'+c if c in "\\'[],;" else c for c in option)
        streams.append(f"amovie=filename={escaped},atrim=start={offset:.6f}:duration={length:.6f},asetpts=PTS-STARTPTS,adelay={round(delay*1000)}:all=1[r{len(streams)}]")
    if not streams:return base
    return base+'[base];'+';'.join(streams)+';[base]'+''.join(f'[r{i}]' for i in range(len(streams)))+f'amix=inputs={len(streams)+1}:duration=first:normalize=0,alimiter=limit=0.95:level=false:latency=true'
