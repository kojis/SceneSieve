"""Seekable filtered soundtrack, shared with the media-export audio pipeline."""
import hashlib,json
from pathlib import Path
import media

def cache_path(folder,video,doc,categories,padding,video_effects=False):
    source=Path(video);stat=source.stat()
    identity={'version':2,'path':str(source.resolve()),'size':stat.st_size,
              'mtime':stat.st_mtime_ns,'doc':doc,'categories':sorted(categories),
              'padding':padding}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    return Path(folder)/(('playback-video-'+key+'.mp4') if video_effects else ('playback-audio-'+key+'.flac'))

def prepare(path,video,doc,categories,padding,progress,cancel,video_effects=False):
    if not video_effects and not any(s['codec_type']=='audio' for s in media.probe(video)):return None
    progress('Preparing filtered video for playback...' if video_effects else 'Preparing filtered audio for playback...')
    return media.export_media(video,doc,path,categories,padding,
                              bool(doc.get('normalize_audio')),progress,cancel,not video_effects)
