"""Start a workspace-local Ollama runtime when one has been provisioned."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import time
import urllib.request

from paths import DATA, AI, MODELS, HOST, FROZEN
PROCESS=None

def alive():
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://'+HOST+'/api/version',timeout=1) as response:
            return bool(json.load(response).get('version'))
    except Exception:
        return False

def start():
    global PROCESS
    if alive():return
    executable=AI/('ollama.exe' if os.name=='nt' else 'bin/ollama')
    if os.name!='nt' and not executable.exists() and shutil.which('ollama'):executable=Path(shutil.which('ollama'))
    if not executable.exists():
        raise RuntimeError('Local AI runtime missing. Restart SceneSieve to repair downloads.')
    state=DATA/'ollama-state';state.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    env.update({'OLLAMA_HOST':HOST,'OLLAMA_MODELS':str(MODELS),
                'OLLAMA_NO_CLOUD':'1','USERPROFILE':str(state)})
    with open(state/'server.log','ab') as log:
        PROCESS=subprocess.Popen([str(executable),'serve'],env=env,cwd=state,stdout=log,stderr=log,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(120):
        if alive():return
        time.sleep(.5)
    raise RuntimeError('Local AI did not start. Check '+str(state/'server.log'))

def stop():
    global PROCESS
    if PROCESS is not None and PROCESS.poll() is None:
        # Unload models before terminating the server so GPU runner children exit.
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://'+HOST+'/api/ps',timeout=5) as response:
                running=json.load(response).get('models',[])
            for model in running:
                request=urllib.request.Request('http://'+HOST+'/api/generate',
                    data=json.dumps({'model':model['name'],'keep_alive':0}).encode(),
                    headers={'Content-Type':'application/json'})
                with opener.open(request,timeout=15) as response:response.read()
        except Exception:
            pass
        PROCESS.terminate()
        try:PROCESS.wait(timeout=10)
        except subprocess.TimeoutExpired:PROCESS.kill();PROCESS.wait(timeout=5)
    PROCESS=None

if __name__=='__main__':start()
