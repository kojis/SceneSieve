"""Player sidecars. Rendered media is required for full audio fidelity."""
from pathlib import Path
from xml.etree.ElementTree import Element,SubElement,tostring,register_namespace
import core
FORMATS={'Kodi EDL':'.edl','MPlayer EDL':'.edl','mpv EDL':'.mpv.edl','VLC playlist':'.xspf'}
def limitation(kind,doc):
    audio=[s for s in doc['scenes'] if s['enabled'] and s.get('action') in ('duck','gain','bleep','replace','distort')]
    if kind in ('Kodi EDL','MPlayer EDL'):
        message='Preserves video cuts and complete mutes. Bleeps, spoken substitutions and distortion become mutes. Partial volume changes, gain, normalization and subtitle changes are not included.'
    else:message='Preserves video cuts only. Audio muting, volume changes, bleeps, spoken substitutions, distortion, normalization and filtered subtitles are not included.'
    if kind=='VLC playlist':message+=' Retained sections are separate playlist entries; transitions may pause and seeking depends on VLC/version.'
    message+=f'\nThis project has {len(audio)} enabled audio adjustments'+(' and normalization enabled.' if doc.get('normalize_audio') else '.')
    message+='\nPixelate, Blur, More blur and Freeze frame are not included in player sidecars. Export filtered video to preserve these visual effects.'
    return message+'\nExport filtered video/audio to preserve the complete edits. Keep this sidecar with the original media, not an already filtered export.'
def intervals(doc,categories,padding):
    ranges=core.kept_ranges(doc['duration'],core.cuts(doc,categories,padding))
    if not ranges:raise ValueError('No video remains after filtering.')
    return ranges

def mplayer_edl(doc,categories,padding):
    cuts=core.cuts(doc,categories,padding)
    mutes=sorted((s['start'],s['end']) for s in doc['scenes'] if s['enabled'] and (s['action'] in ('bleep','replace','distort') or s['action']=='duck' and s.get('level',0)==0))
    merged=[]
    for a,b in mutes:
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    rows=[(a,b,0) for a,b in cuts]
    for a,b in merged:
        for x,y in core.kept_ranges(doc['duration'],cuts):
            lo,hi=max(a,x),min(b,y)
            if hi>lo:rows.append((lo,hi,1))
    return ''.join(f'{a:.3f} {b:.3f} {action}\n' for a,b,action in sorted(rows))

def export_text(kind,video,doc,categories,padding):
    if kind in ('Kodi EDL','MPlayer EDL'):return mplayer_edl(doc,categories,padding)
    if kind=='mpv EDL':return core.mpv_edl(video,doc,categories,padding)
    ns='http://xspf.org/ns/0/';vlc='http://www.videolan.org/vlc/playlist/ns/0/';register_namespace('',ns);register_namespace('vlc',vlc)
    root=Element('{'+ns+'}playlist',{'version':'1'});SubElement(root,'{'+ns+'}title').text='SceneSieve filtered segments';tracks=SubElement(root,'{'+ns+'}trackList')
    for i,(a,b) in enumerate(intervals(doc,categories,padding)):
        track=SubElement(tracks,'{'+ns+'}track');SubElement(track,'{'+ns+'}location').text=Path(video).resolve().as_uri();SubElement(track,'{'+ns+'}title').text=f'Segment {i+1}: {core.clock(a)} – {core.clock(b)}'
        ext=SubElement(track,'{'+ns+'}extension',{'application':'http://www.videolan.org/vlc/playlist/0'})
        SubElement(ext,'{'+vlc+'}option').text=f'start-time={a:.6f}';SubElement(ext,'{'+vlc+'}option').text=f'stop-time={b:.6f}'
    return '<?xml version="1.0" encoding="UTF-8"?>\n'+tostring(root,encoding='unicode')+'\n'
