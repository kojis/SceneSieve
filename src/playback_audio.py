"""Seekable filtered soundtrack, shared with the media-export audio pipeline."""
import hashlib,json
from pathlib import Path
import media

def cache_path(folder,video,doc,categories,padding):
    source=Path(video);stat=source.stat()
    identity={'version':1,'path':str(source.resolve()),'size':stat.st_size,
              'mtime':stat.st_mtime_ns,'doc':doc,'categories':sorted(categories),
              'padding':padding}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    return Path(folder)/('playback-audio-'+key+'.flac')

def prepare(path,video,doc,categories,padding,progress,cancel):
    if not any(s['codec_type']=='audio' for s in media.probe(video)):return None
    progress('Preparing filtered audio for playback...')
    return media.export_media(video,doc,path,categories,padding,
                              bool(doc.get('normalize_audio')),progress,cancel,True)
