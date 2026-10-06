"""Vision catalog and cancellable Ollama model downloads."""
import json,re,urllib.request,concurrent.futures,time
from pathlib import Path
import scanner
from paths import DATA
CATALOG=['gemma3:4b','gemma3:12b','gemma3:27b','qwen3-vl:2b','qwen3-vl:4b','qwen3-vl:8b','qwen3-vl:30b','qwen3-vl:32b','qwen3-vl:235b','qwen2.5vl:3b','qwen2.5vl:7b','qwen2.5vl:32b','qwen2.5vl:72b','minicpm-v4.5:latest','minicpm-v:latest','llama3.2-vision:11b','llama3.2-vision:90b','llava:7b','llava:13b','llava:34b','llava-phi3:latest','llava-llama3:latest','bakllava:latest','moondream:latest','granite3.2-vision:latest','mistral-small3.1:latest','mistral-small3.2:latest']
def catalog(online=False):
    cache=DATA/'vision-catalog.json';names=set(CATALOG)
    try:names.update(json.loads(cache.read_text()))
    except (OSError,ValueError):pass
    if online:
        try:
            def page(url):
                req=urllib.request.Request(url,headers={'User-Agent':'SceneSieve/2.0'})
                with urllib.request.urlopen(req,timeout=20) as r:return r.read().decode()
            html=page('https://ollama.com/library')
            families={name for name,body in re.findall(r'<a\b[^>]*href="/library/([^"/]+)"[^>]*>(.*?)</a>',html,re.S) if re.search(r'>\s*vision\s*<',body)}
            def tags(family):
                try:
                    html=page('https://ollama.com/library/'+family+'/tags')
                    return {name for name,body in re.findall(r'<a\b[^>]*href="/library/([^"/]+:[^"]+)"[^>]*>(.*?)</a>',html,re.S) if 'Image' in body and not any(x in name.lower() for x in ('cloud','mlx'))}
                except OSError:return set()
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                for found in pool.map(tags,families):names.update(found)
            DATA.mkdir(parents=True,exist_ok=True);cache.write_text(json.dumps(sorted(names)))
        except OSError:pass
    installed=scanner.local_models()
    names.update(installed)
    return sorted(n for n in names if 'cloud' not in n.lower()),set(installed)
def ensure_model(name,progress,cancel):
    if not re.fullmatch(r'[A-Za-z0-9_.:/-]+',name) or 'cloud' in name.lower():raise ValueError('Choose a local Ollama vision model.')
    if name not in scanner.local_models():
        progress('Downloading vision model '+name+'...')
        req=urllib.request.Request(scanner.API+'pull',data=json.dumps({'model':name,'stream':True}).encode(),headers={'Content-Type':'application/json'})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),scanner.NoRedirect())
        success=False
        with opener.open(req,timeout=90) as r:
            for line in r:
                if cancel.is_set():raise InterruptedError('Download cancelled. Scan again to resume.')
                item=json.loads(line)
                if item.get('error'):raise RuntimeError(item['error'])
                total=item.get('total',0);pct=f" {100*item.get('completed',0)/total:.0f}%" if total else ''
                progress(name+': '+item.get('status','Downloading')+pct)
                success=item.get('status')=='success'
        if not success:raise RuntimeError('Model download did not complete. Scan again to resume.')
    info=scanner.request('show',{'model':name},timeout=30)
    if 'vision' not in info.get('capabilities',[]) or info.get('remote_host'):raise ValueError('This model is not a local vision model.')
def family_description(family):
    name=family.lower()
    if 'gemma' in name:return 'General image understanding. Smaller variants suit faster scans; larger variants need more memory. Gore accuracy is not benchmarked.'
    if 'qwen' in name:return 'Detailed image understanding. Choose an instruct/local variant; larger sizes cost more memory and scan time. Review gore detections.'
    if 'minicpm' in name:return 'Compact image/video understanding family. A candidate for local scanning; compare errors and speed on your footage.'
    if 'granite' in name:return 'Primarily document/chart vision. Available for comparison; not specialized or validated for gore detection.'
    if 'moondream' in name or 'phi' in name:return 'Compact vision model; lower resource use, but fine visual details may be harder to classify.'
    if 'llava' in name:return 'Earlier general-purpose vision family. Useful for comparison; inspect detailed or ambiguous detections carefully.'
    return 'Local vision family. Variant size/quantization controls memory and speed; detection quality on your footage is not yet measured.'
def group_variants(names):
    grouped={}
    for name in names:
        family,_,tag=name.partition(':');grouped.setdefault(family,[]).append(name)
    for family in grouped:grouped[family]=sorted(set(grouped[family]),key=lambda n:('q4' not in n.lower(),len(n),n))
    return grouped
