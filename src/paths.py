"""Downloaded runtime and user data locations."""
import os,sys
from pathlib import Path
FROZEN=bool(getattr(sys,'frozen',False))
ROOT=Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
if os.name=='nt':default_base=Path(os.environ.get('LOCALAPPDATA',str(ROOT)))/'SceneSieve'
elif sys.platform=='darwin':default_base=Path.home()/'Library/Application Support/SceneSieve'
else:default_base=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'SceneSieve'
BASE=Path(os.environ.get('SCENESIEVE_HOME',str(default_base)))
DATA=Path(os.environ.get('SCENESIEVE_DATA_DIR',str(BASE/'data')))
ASSETS=BASE/'assets'
AI=ASSETS/'ollama'
MODELS=BASE/'models'/'vision'
HOST='127.0.0.1:11435'
BIN=ASSETS/'bin'
SETTINGS=DATA/'settings.json'
