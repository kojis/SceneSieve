"""Subtitle matching via public Internet Archive metadata and OpenSubtitles REST."""
import json,re,struct,urllib.request,urllib.parse,urllib.error,concurrent.futures,difflib
from pathlib import Path
USER_AGENT='SceneSieve v2.2'
def request(url,data=None,key=''):
    headers={'User-Agent':USER_AGENT,'Accept':'application/json'}
    if key:headers['Api-Key']=key
    if data is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=None if data is None else json.dumps(data).encode(),headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Subtitle provider returned HTTP {e.code}. Check your API key, account download allowance, or try another source.') from None

def title_guess(video):
    text=Path(video).stem.replace('.',' ').replace('_',' ')
    return re.split(r'\b(?:19\d\d|20\d\d|2160p|1080p|720p|WEB[- ]?DL|BluRay|x26[45])\b',text,flags=re.I)[0].strip(' -')
def movie_hash(video):
    p=Path(video);size=p.stat().st_size
    if size<131072:return None
    with p.open('rb') as f:
        first=f.read(65536);f.seek(-65536,2);last=f.read(65536)
    return f'{(size+sum(struct.unpack("<8192Q",first))+sum(struct.unpack("<8192Q",last)))&0xffffffffffffffff:016x}'
def score(query,title,hash_match=False):
    if hash_match:return 'File hash match'
    clean=lambda s:re.sub(r'[^\w]+',' ',str(s).casefold()).strip()
    return f'Title similarity {round(100*difflib.SequenceMatcher(None,clean(query),clean(title)).ratio())}% — verify timing'
def search_archive(query,language='en'):
    q='mediatype:movies AND title:("'+query.replace('"','').replace('\\','')+'")'
    url='https://archive.org/advancedsearch.php?'+urllib.parse.urlencode({'q':q,'fl[]':['identifier','title'],'rows':20,'output':'json'},doseq=True)
    items=request(url).get('response',{}).get('docs',[])
    def matches(item):
        identifier=item['identifier'];data=request('https://archive.org/metadata/'+urllib.parse.quote(identifier,safe=''))
        metadata=data.get('metadata',{});rights=metadata.get('licenseurl') or metadata.get('rights') or 'Rights not specified by uploader'
        if isinstance(rights,list):rights='; '.join(map(str,rights))
        out=[]
        for f in data.get('files',[]):
            name=f.get('name','')
            if f.get('private') or Path(name).suffix.lower() not in ('.srt','.vtt','.ass','.ssa'):continue
            out.append({'provider':'Internet Archive','title':item.get('title',identifier),'file':name,'language':str(metadata.get('language','unspecified')),'match':score(query,item.get('title',identifier)),'rights':str(rights),'url':'https://archive.org/download/'+urllib.parse.quote(identifier,safe='')+'/'+urllib.parse.quote(name,safe='/'),'page':'https://archive.org/details/'+urllib.parse.quote(identifier,safe='')})
        return out
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(matches,item) for item in items]
        for future in futures:
            try:results.extend(future.result())
            except (OSError,ValueError):continue
    return sorted(results,key=lambda r:difflib.SequenceMatcher(None,query.casefold(),str(r['title']).casefold()).ratio(),reverse=True)

def search_opensubtitles(video,query,language,key):
    if not key.strip():raise ValueError('OpenSubtitles requires your own API key (free account/API allowance subject to provider limits). Internet Archive does not require a key.')
    params={'query':query,'languages':language};h=movie_hash(video)
    if h:params['moviehash']=h
    data=request('https://api.opensubtitles.com/api/v1/subtitles?'+urllib.parse.urlencode(params),key=key)
    results=[]
    for item in data.get('data',[]):
        a=item.get('attributes',{});release=a.get('release','');title=a.get('feature_details',{}).get('title') or release
        for f in a.get('files',[]):
            results.append({'provider':'OpenSubtitles','title':title,'file':f.get('file_name',release),'language':a.get('language',''),'match':score(query,title,a.get('moviehash_match',False)),'rights':'Provider/uploader terms; free access is not an open-content licence','file_id':f['file_id'],'page':a.get('url','https://www.opensubtitles.com')})
    return results

def download(result,duration,key=''):
    import media
    url=result.get('url')
    if result['provider']=='OpenSubtitles':
        response=request('https://api.opensubtitles.com/api/v1/download',{'file_id':result['file_id']},key)
        url=response.get('link')
    if not url:raise RuntimeError('The provider did not return a subtitle download link.')
    return media.download_subtitles(url,duration)
