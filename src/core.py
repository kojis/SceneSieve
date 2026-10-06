"""Scene documents and deterministic playback plans. Times are source seconds."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time

VERSION = 1

def number(value):
    if isinstance(value, bool):
        raise ValueError('A timestamp must be a number.')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Timestamps must be finite.')
    return value

def timestamp(text):
    parts = str(text).strip().split(':')
    if not 1 <= len(parts) <= 3:
        raise ValueError('Use seconds or HH:MM:SS.mmm.')
    values = [number(p) for p in parts]
    if any(v < 0 for v in values) or (len(values) > 1 and any(v >= 60 for v in values[1:])):
        raise ValueError('Invalid timestamp.')
    return sum(v * 60 ** i for i, v in enumerate(reversed(values)))

def clock(t):
    ms = round(t * 1000)
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}'

def fingerprint(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return {'sha256': h.hexdigest(), 'size': Path(path).stat().st_size}

def validate(doc, identity=None):
    if doc.get('version') != VERSION:
        raise ValueError('Unsupported scene-file version.')
    duration = number(doc['duration'])
    if duration <= 0:
        raise ValueError('The video duration must be positive.')
    if identity is not None and doc['fingerprint'] != identity:
        raise ValueError('This scene file belongs to a different video. No scenes were loaded.')
    if not isinstance(doc['scenes'], list):
        raise ValueError('Scenes must be a list.')
    for s in doc['scenes']:
        a, b = number(s['start']), number(s['end'])
        if not 0 <= a < b <= duration:
            raise ValueError('Every scene must have 0 ≤ start < end ≤ video duration.')
        if not isinstance(s['category'], str) or not s['category'].strip():
            raise ValueError('Every scene needs a category.')
        if s.get('action') not in ('skip','duck','gain','bleep','replace','distort','pixelate','blur','blur_strong','freeze'):
            raise ValueError('Unsupported scene action.')
        if s['action']=='duck' and not 0<=number(s.get('level',0))<=1:raise ValueError('Audio level must be between zero and one.')
        if s['action']=='gain' and not -60<=number(s.get('gain_db',0))<=24:raise ValueError('Audio gain is out of range.')
        if s['action'] in ('bleep','replace'):
            if not 0<=number(s.get('replacement_level',.15))<=1:raise ValueError('Replacement level must be between zero and one.')
            if not 100<=number(s.get('frequency',1000))<=4000:raise ValueError('Bleep frequency must be 100–4000 Hz.')
            if s['action']=='replace' and (not isinstance(s.get('replacement'),str) or not 1<=len(s['replacement'].strip())<=120):raise ValueError('Enter a replacement phrase of 1–120 characters.')
        if type(s.get('enabled')) is not bool or type(s.get('reviewed')) is not bool:
            raise ValueError('Enabled and reviewed must be boolean values.')
    return doc

def atomic_text(path, text):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        for attempt in range(6):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 5:raise
                # Windows indexers/virus scanners can briefly hold an existing file.
                time.sleep(.05 * 2 ** attempt)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def save(path, doc):
    validate(doc)
    atomic_text(path, json.dumps(doc, indent=2, ensure_ascii=False) + '\n')

def cuts(doc, categories=None, padding=0):
    validate(doc)
    padding = number(padding)
    if padding < 0:
        raise ValueError('Padding cannot be negative.')
    ranges = sorted((max(0, number(s['start']) - padding), min(doc['duration'], number(s['end']) + padding))
                    for s in doc['scenes'] if s['enabled'] and s.get('action')=='skip' and (categories is None or s['category'] in categories))
    merged = []
    for a, b in ranges:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged

def kept_ranges(duration, excluded):
    result, cursor = [], 0.0
    for a, b in excluded:
        if a > cursor:
            result.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < duration:
        result.append((cursor, duration))
    return result

def mpv_edl(video, doc, categories=None, padding=0):
    ranges = kept_ranges(doc['duration'], cuts(doc, categories, padding))
    if not ranges:
        raise ValueError('These filters exclude the entire video.')
    return _mpv_ranges(video,ranges)

def mpv_clip(video, start, end, duration):
    start,end,duration=number(start),number(end),number(duration)
    if not 0 <= start < end <= duration:
        raise ValueError('Preview boundaries must be within the video.')
    return _mpv_ranges(video,[(start,end)])

def _mpv_ranges(video,ranges):
    path = str(Path(video).resolve()).replace('\\', '/')
    if '\n' in path or '\r' in path:
        raise ValueError('Newlines in video filenames are unsupported.')
    # mpv length escaping counts UTF-8 bytes, not Python characters.
    escaped = f'%{len(path.encode("utf-8"))}%{path}'
    return '# mpv EDL v0\n' + ''.join(f'{escaped},{a:.6f},{b-a:.6f}\n' for a,b in ranges)

def kodi_edl(doc, categories=None, padding=0):
    entries=[(a,b,0) for a,b in cuts(doc,categories,padding)]
    entries.extend((s['start'],s['end'],1) for s in doc['scenes'] if s['enabled'] and (s.get('action') in ('bleep','replace','distort') or (s.get('action')=='duck' and s.get('level',0)==0)))
    return ''.join(f'{a:.3f} {b:.3f} {action}\n' for a,b,action in sorted(entries))
