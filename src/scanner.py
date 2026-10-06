"""Experimental local vision scanning via Ollama; no remote endpoints."""
import base64
import json
import math
import hashlib
from pathlib import Path
import urllib.request
import urllib.error
import cv2
import core

from paths import HOST
API = 'http://' + HOST + '/api/'

class ModelResponseError(ValueError):
    """The local model did not return a usable classification."""

def request(endpoint, data=None, timeout=180):
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(API + endpoint, data=payload, headers={'Content-Type': 'application/json'})
    # Ignore HTTP proxy environment variables for local video data.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            try:
                result = json.load(response)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ModelResponseError('Ollama returned an empty or invalid API response.') from e
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            body = json.loads(e.read())
            if isinstance(body, dict):detail = str(body.get('error', ''))[:300]
        except (ValueError, UnicodeDecodeError):pass
        raise ModelResponseError(f'Ollama request failed (HTTP {e.code}). {detail}'.strip()) from e
    if not isinstance(result, dict):
        raise ModelResponseError('Ollama returned an unexpected API response.')
    if result.get('error'):
        raise ModelResponseError('Ollama reported an inference error: ' + str(result['error'])[:300])
    return result

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirects are disabled for local inference.')

def local_models():
    models = request('tags', timeout=5).get('models', [])
    result = []
    for item in models:
        name = item['name']
        if 'cloud' in name.lower() or item.get('remote_host') or item.get('remote_model'):
            continue
        info = request('show', {'model': name}, timeout=10)
        if not info.get('remote_host') and not info.get('remote_model') and 'vision' in info.get('capabilities', []):
            result.append(name)
    return result

def probe(path):
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not cap.isOpened() or not math.isfinite(fps) or fps <= 0 or frames <= 0:
            raise ValueError('Cannot read this video. Try a local MP4 or MKV file.')
        return frames / fps
    finally:
        cap.release()

def parse_categories(result, categories):
    if not isinstance(result, dict) or result.get('error'):
        raise ModelResponseError('The model reported an inference error.')
    raw = result.get('response')
    if not isinstance(raw, str) or not raw.strip():
        raise ModelResponseError('The model returned no classification text.')
    raw = raw.strip()
    # Accept a single Markdown JSON fence, but never guess from arbitrary prose.
    lines = raw.splitlines()
    if len(lines) >= 3 and lines[0].strip().lower() in ('```json', '```') and lines[-1].strip() == '```':
        raw = '\n'.join(lines[1:-1])
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ModelResponseError('The model returned malformed classification JSON.') from e
    if not isinstance(value, dict) or set(value) != {'categories'}:
        raise ModelResponseError('The model did not return the required categories object.')
    labels = value['categories']
    if not isinstance(labels, list) or any(not isinstance(x, str) or x not in categories for x in labels):
        raise ModelResponseError('The model returned invalid categories.')
    return labels

GORE_DETAILS = ['exposed internal organs', 'severed body part',
                'open wound exposing deep tissue or bone', 'visibly mutilated body']

def classify(frame, model, categories, cancelled=None, strict_gore=True, precision=None):
    if precision is None:labels = _classify_frame(frame, model, categories, cancelled)
    else:
        precision=max(0,min(100,int(precision)));strict_gore=precision>=75
        policy=('Include even plausible, ambiguous, obscured or brief indications. Prefer false positives to missed content. Gore includes suspected injury, blood or disturbing bodily harm; mature subject matter includes threatening violence, sexual themes or self-harm.' if precision==0 else
                'Include plausible matches even when details are uncertain; lean toward filtering possible adult material.' if precision==25 else
                'Include likely visible matches, but do not guess from mood or genre alone.' if precision==50 else
                'Require clearly visible evidence; omit ambiguous or inferred matches.' if precision==75 else
                'Require unmistakable direct visual evidence; reject small, blurred, uncertain or inferred matches.')
        labels=_classify_frame(frame,model,categories,cancelled,prompt='Assess this frame for the allowed content categories. '+policy+' Return only a JSON object with a categories array containing matching allowed labels, or an empty array. Allowed labels: '+json.dumps(categories))
    gore_labels = [label for label in labels if label.casefold() == 'gore']
    if strict_gore and gore_labels:
        details = _classify_frame(frame, model, GORE_DETAILS, cancelled, prompt=(
            'Inspect this image for directly visible severe anatomical injury. '
            'Do not infer injury from the genre, dialogue, mood, a weapon, a prone person, '
            'a corpse with intact skin, blood stains, red lighting, shadows, a face, fangs, '
            'an attack, food, makeup, or an obscured area. Blood alone is not sufficient. '
            'Only include an allowed label when that precise anatomical detail is clearly '
            'visible. If details are ambiguous, blurred, hidden, or too small, return '
            '{"categories": []}. Return only a JSON object with a categories array. '
            'Allowed labels: ' + json.dumps(GORE_DETAILS)))
        if not details:
            labels = [label for label in labels if label not in gore_labels]
    other_labels=[label for label in labels if label.casefold()!='gore']
    if strict_gore and other_labels:
        confirmed=_classify_frame(frame,model,other_labels,cancelled,prompt=(
            'Verify these candidate labels against directly visible evidence in this single frame. '
            'Be conservative: remove any label whose evidence is ambiguous, small, blurred, hidden, '
            'or inferred from context, genre or appearance alone. '
            'Violence requires a visible physical attack, not merely a weapon or threatening pose. '
            'Nudity requires clearly visible uncovered intimate anatomy, not swimwear or skin-colored clothing. '
            'Drugs requires clearly identifiable drug substances, paraphernalia or use; do not infer it from an ordinary drink, smoke or an unidentified pill alone. '
            'Bugs and spiders requires a clearly visible insect, arachnid or infestation, not shadows or patterns. '
            'Blood requires identifiable blood rather than red objects, lighting or food. '
            'Mature subject matter requires explicit visible adult themes such as sexual activity or self-harm; '
            'do not infer it from dialogue, mood or an ordinary adult person. '
            'For any custom category, require unambiguous visible evidence of its literal meaning. '
            'Return only a JSON object with a categories array containing verified allowed labels, '
            'or {"categories": []} if none can be verified. Allowed labels: '+json.dumps(other_labels)))
        labels=[label for label in labels if label.casefold()=='gore' or label in confirmed]
    return labels

def _classify_frame(frame, model, categories, cancelled=None, prompt=None):
    h,w = frame.shape[:2]
    frame = cv2.resize(frame, (max(1, round(w * min(1, 768/max(w,h)))), max(1, round(h * min(1, 768/max(w,h))))))
    ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError('Cannot encode a video frame.')
    schema = {'type':'object', 'properties':{'categories':{'type':'array','items':{'type':'string','enum':categories}}}, 'required':['categories'], 'additionalProperties':False}
    payload = {
        'model':model, 'stream':False, 'think':False, 'options':{'temperature':0, 'num_predict':128, 'repeat_penalty':1.15},
        'prompt':prompt or ('Classify only content clearly visible in this single image. Return only a JSON object '
                 'with a categories array containing allowed labels, or {"categories": []} when none apply. '
                 'Gore requires visible exposed organs, severed body parts, a deep open wound exposing tissue '
                 'or bone, or visible bodily mutilation. Blood alone, minor cuts, bruises, intact corpses, '
                 'unconscious people, threatening expressions, fangs, darkness, weapons, or a fight without '
                 'graphic injury are NOT gore. Do not infer gore from context or genre. '
                 'Blood requires clearly identifiable blood, not red lighting, clothing, paint, or food. '
                 'Violence means a visible physical attack or fight. Omit a category if uncertain. '
                 'Custom labels describe visible content. Allowed labels: ' + json.dumps(categories)),
        'images':[base64.b64encode(jpg).decode('ascii')]}
    # Some Ollama grammar failures return HTTP 200 with an empty response.
    # Retry the same frame with less restrictive generation, validating every result.
    for attempt_index, output_format in enumerate((schema, 'json', None)):
        if cancelled is not None and cancelled.is_set():
            raise InterruptedError('Scan cancelled. Existing scenes are unchanged.')
        attempt = dict(payload)
        if attempt_index:
            attempt['options'] = {**payload['options'], 'temperature':0.15, 'seed':attempt_index}
        if output_format is not None:
            attempt['format'] = output_format
        try:
            return parse_categories(request('generate', attempt), categories)
        except ModelResponseError as e:
            last_error = e
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError('Scan cancelled. Existing scenes are unchanged.')
            if attempt_index == 0:
                # A failed grammar can leave the runner repeatedly returning empty
                # output or token-repeat errors. Unload once to clear that state.
                try:
                    request('generate', {'model': model, 'keep_alive': 0})
                except ModelResponseError:
                    pass  # Still try the remaining independently validated attempts.
    raise ModelResponseError(f'Local model {model} could not classify this frame after 3 attempts. '
                             f'{last_error} Try a different local vision model.') from last_error

class Checkpoint:
    """Cache validated observations only, keyed to the exact video and scan settings."""
    def __init__(self, directory, identity, duration, model, categories, step, strict_gore=True, precision=None):
        self.metadata = {'version':4, 'video':identity, 'duration':float(duration),
                         'model':model, 'categories':sorted(categories), 'step':float(step),
                         'strict_gore':bool(strict_gore),'precision':precision}
        key = hashlib.sha256(json.dumps(self.metadata, sort_keys=True).encode()).hexdigest()
        self.path = Path(directory) / (key + '.json')
        self.observations = {}
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding='utf-8'))
                if saved.get('metadata') != self.metadata:return
                entries = saved['observations']
                if not isinstance(entries, dict):return
                valid = {}
                for timestamp, labels in entries.items():
                    t = float(timestamp)
                    if not math.isfinite(t) or not 0 <= t < duration:return
                    if not isinstance(labels, list) or any(not isinstance(s, str) or s not in categories for s in labels):return
                    valid[t] = labels
                self.observations = valid
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                pass  # A corrupt checkpoint is recomputed, never interpreted as clear.
    def record(self, timestamp, labels):
        self.observations[timestamp] = labels
        self.path.parent.mkdir(parents=True, exist_ok=True)
        core.atomic_text(self.path, json.dumps({'metadata':self.metadata,'observations':self.observations}))

def scan(path, duration, model, categories, step, cancelled, progress, cache_dir=None, identity=None, strict_gore=True, precision=None):
    if model not in local_models():
        raise ValueError('Select an installed local vision model. Cloud models are not supported.')
    checkpoint = None
    if cache_dir is not None:
        checkpoint = Checkpoint(cache_dir, identity or core.fingerprint(path), duration, model, categories, step, strict_gore, precision)
    observations = dict(checkpoint.observations) if checkpoint else {}
    if observations:
        progress(f'Resuming with {len(observations)} previously classified frames.')
    cap = cv2.VideoCapture(str(path))
    def sample(t):
        if cancelled.is_set():
            raise InterruptedError('Scan cancelled. Existing scenes are unchanged.')
        if t in observations:return
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f'Cannot decode the frame near {t:.1f}s. No scan results were applied.')
        try:
            observations[t] = classify(frame, model, categories, cancelled=cancelled, strict_gore=strict_gore, **({"precision":precision} if precision is not None else {}))
        except ModelResponseError as e:
            recovery = (' Completed frames are saved; Scan / resume reuses them with the same model and settings.'
                        if checkpoint else '')
            raise ModelResponseError(f'Scan stopped near {t:.1f}s: {e}{recovery}') from e
        if checkpoint:
            checkpoint.record(t, observations[t])
        if cancelled.is_set():
            raise InterruptedError('Scan cancelled. Existing scenes are unchanged.')
    try:
        times = [i * step for i in range(math.ceil(duration / step))]
        progress(f'Scanning 0/{len(times)} frames')
        for i,t in enumerate(times):
            sample(t)
            progress(f'Scanning {i+1}/{len(times)} frames • {t:.1f}s / {duration:.1f}s')
        refine = set()
        for t in times:
            labels = observations[t]
            if labels:
                a, b = max(0,t-step), min(duration,t+step)
                refine.update(round(a+i*0.5, 3) for i in range(math.ceil((b-a)/0.5)))
        refinement=sorted(refine - observations.keys())
        if refinement:progress(f'Refining flagged scenes 0/{len(refinement)} frames')
        for i,t in enumerate(refinement):
            sample(t)
            progress(f'Refining flagged scenes {i+1}/{len(refinement)} frames')
        scenes = []
        # Conservative support around every positive sample; coarse misses remain possible.
        for category in categories:
            intervals = sorted((max(0,t-step/2),min(duration,t+step/2)) for t,labels in observations.items() if category in labels)
            merged=[]
            for a,b in intervals:
                if merged and a <= merged[-1][1]:
                    merged[-1][1]=max(merged[-1][1],b)
                else:
                    merged.append([a,b])
            scenes.extend({'start':a,'end':b,'category':category,'action':'skip','enabled':True,'reviewed':False,'source':'ollama:'+model} for a,b in merged)
        return sorted(scenes,key=lambda s:s['start'])
    finally:
        cap.release()
