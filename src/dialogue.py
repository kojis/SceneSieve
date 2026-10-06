"""Readable display excerpts without changing the original word timings."""
import re

def excerpts(cues):
    result=[];pending=None
    for cue in cues:
        text=cue.get('text','').strip()
        if not text:continue
        word=cue.get('precision')=='word'
        if not word:
            if pending:result.append(pending);pending=None
            result.append(dict(cue));continue
        if pending and (cue['start']-pending['end']>.8 or cue['end']-pending['start']>7 or len(pending['text'])+len(text)+1>110):
            result.append(pending);pending=None
        if pending:
            separator='' if re.match(r'^[,.;:!?]',text) else ' '
            pending['text']+=separator+text;pending['end']=max(pending['end'],cue['end'])
        else:pending=dict(cue,text=text)
        if re.search(r'[.!?][\"\u201d\u2019]*$',text):result.append(pending);pending=None
    if pending:result.append(pending)
    return result
