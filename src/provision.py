"""First-launch installer: pinned assets, user-local paths, restartable setup."""
import hashlib,json,os,shutil,sys,urllib.request,zipfile,tempfile,importlib,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path(os.environ['SCENESIEVE_HOME']);CACHE=BASE/'downloads';ASSETS=BASE/'assets';LIB=BASE/'python-3.12.10'/'Lib'/'site-packages'
MANIFEST=json.loads((ROOT/'runtime-manifest.json').read_text())
def digest(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def status(text):print(text,flush=True)
def download(item):
 CACHE.mkdir(parents=True,exist_ok=True);p=CACHE/item['name']
 if p.exists() and digest(p)==item['sha256']:return p
 part=p.with_suffix(p.suffix+'.partial')
 for attempt in range(3):
  try:
   status('Downloading '+item['name'])
   with urllib.request.urlopen(item['url'],timeout=60) as r,part.open('wb') as f:
    total=int(r.headers.get('Content-Length',0));done=0;last=-1
    while chunk:=r.read(1024*1024):
     f.write(chunk);done+=len(chunk);pct=int(done*100/total) if total else 0
     if pct!=last:status(item['name']+f' — {done//1048576} MB'+(f' ({pct}%)' if total else ''));last=pct
   if digest(part)!=item['sha256']:raise RuntimeError('Download checksum mismatch: '+item['name'])
   part.replace(p);return p
  except Exception:
   if attempt==2:raise

def safe_zip(archive,dest):
 with zipfile.ZipFile(archive) as z:
  for info in z.infolist():
   p=(dest/info.filename).resolve()
   if not p.is_relative_to(dest.resolve()):raise RuntimeError('Unsafe archive path')
  z.extractall(dest)
def record(directory,marker):
 files={}
 for p in directory.rglob('*'):
  if p.is_file() and p.name!=marker.name and '__pycache__' not in p.parts:
   stat=p.stat();files[str(p.relative_to(directory))]={'sha256':digest(p),'size':stat.st_size,'mtime':stat.st_mtime_ns}
   if len(files)%200==0:status(f'Verifying installed files: {len(files)}')
 marker.write_text(json.dumps(files))
def verified(directory,marker):
 try:
  entries=json.loads(marker.read_text())
  if not entries:return False
  for name,record in entries.items():
   p=directory/name
   if not p.is_file():return False
   if isinstance(record,str):
    if digest(p)!=record:return False
   else:
    stat=p.stat()
    if stat.st_size!=record['size']:return False
    if stat.st_mtime_ns!=record['mtime'] and digest(p)!=record['sha256']:return False
  return True
 except (OSError,ValueError):return False

def main():
 LIB.mkdir(parents=True,exist_ok=True);ASSETS.mkdir(parents=True,exist_ok=True)
 lockhash=hashlib.sha256(json.dumps(MANIFEST['wheels'],sort_keys=True).encode()).hexdigest()[:16]
 marker=BASE/('libraries-'+lockhash+'.json');status('Verifying support libraries...')
 if not verified(LIB,marker):
  for item in MANIFEST['wheels']:
   path=download(item);safe_zip(path,LIB)
  # Wheel .data directories need relocation when present.
  for data in LIB.glob('*.data'):
   for kind in ('purelib','platlib'):
    if (data/kind).exists():shutil.copytree(data/kind,LIB,dirs_exist_ok=True)
  record(LIB,marker)
 sys.path.insert(0,str(LIB));importlib.invalidate_caches()
 for item in MANIFEST['assets']:
  directory=ASSETS/item['dest'];marker=ASSETS/(item['dest']+'-'+item['sha256'][:12]+'.json')
  status('Verifying '+item['dest']+'...')
  if not verified(directory,marker):
   path=download(item);directory.mkdir(parents=True,exist_ok=True)
   status('Extracting '+item['dest']+'...')
   if item['format']=='zip':safe_zip(path,directory)
   elif item['format']=='file':shutil.copy2(path,directory/item['name'])
   else:
    result=subprocess.run([str(ASSETS/'archive-tool'/'7zr.exe'),'x',str(path),'-o'+str(directory),'-y'],capture_output=True,creationflags=0x08000000)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace')[-1000:])
   record(directory,marker)
 bindir=ASSETS/'bin';bindir.mkdir(exist_ok=True)
 for name,folder in [('mpv.exe','mpv'),('ffmpeg.exe','ffmpeg'),('ffprobe.exe','ffmpeg')]:
  source=next((ASSETS/folder).rglob(name));dest=bindir/name
  if not dest.exists() or digest(dest)!=digest(source):shutil.copy2(source,dest)
 status('Setup verified. Starting SceneSieve...')
if __name__=='__main__':main()
