"""Install release files and platform-specific desktop launchers in user storage."""
import hashlib,os,plistlib,shlex,shutil,subprocess,sys,urllib.request
from pathlib import Path

VERSION='3.20'
def main():
    mac=sys.platform=='darwin'
    if not mac and not sys.platform.startswith('linux'):raise SystemExit('macOS or Linux required.')
    if sys.version_info[:2] not in ((3,10),(3,11),(3,12),(3,13)):
        raise SystemExit('Python 3.10 through 3.13 required; install Python 3.12 and retry.')
    bundle=Path(__file__).resolve().parent
    base=Path(os.environ.get('SCENESIEVE_HOME',str(Path.home()/'Library/Application Support/SceneSieve' if mac else Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'SceneSieve')))
    release=base/'releases'/VERSION;release.mkdir(parents=True,exist_ok=True)
    shutil.copytree(bundle/'src',release,dirs_exist_ok=True)
    shutil.copy2(bundle/'requirements.txt',release/'requirements-unix.txt')
    if not mac and not shutil.which('ollama') and not (base/'assets/ollama/bin/ollama').exists():
        import platform
        arch={'x86_64':'amd64','aarch64':'arm64'}.get(platform.machine())
        if not arch:raise SystemExit('Ollama requires x86_64 or ARM64.')
        folder=base/'assets/ollama';folder.mkdir(parents=True,exist_ok=True)
        archive=folder/'download.tar.zst'
        print('Downloading Ollama from ollama.com...',flush=True)
        urllib.request.urlretrieve('https://ollama.com/download/ollama-linux-'+arch+'.tar.zst',archive)
        subprocess.run(['tar','--zstd','-xf',str(archive),'-C',str(folder)],check=True)
        archive.unlink()
    env=base/('python-'+VERSION);python=env/'bin/python'
    if not python.exists():subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
    subprocess.run([str(python),'-m','pip','install','--upgrade','pip'],check=True)
    subprocess.run([str(python),'-m','pip','install','--only-binary=:all:','-r',str(release/'requirements-unix.txt')],check=True)
    subprocess.run([str(python),'-c','import PySide6,cv2,numpy,pysubs2,faster_whisper'],check=True)
    launcher=base/'launch.sh'
    launcher.write_text('#!/bin/bash\nset -e\nexport PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"\n'+
        'export SCENESIEVE_HOME='+shlex.quote(str(base))+'\n'+
        ('' if mac else 'export QT_QPA_PLATFORM=xcb\n')+
        'exec '+shlex.quote(str(python))+' '+shlex.quote(str(release/'desktop_entry.py'))+' "$@"\n',encoding='utf-8')
    launcher.chmod(0o755)
    if mac:
        app=Path.home()/'Applications/SceneSieve.app/Contents';(app/'MacOS').mkdir(parents=True,exist_ok=True)
        binary=app/'MacOS/SceneSieve';shutil.copy2(launcher,binary);binary.chmod(0o755)
        with (app/'Info.plist').open('wb') as f:plistlib.dump(dict(CFBundleName='SceneSieve',CFBundleExecutable='SceneSieve',CFBundleIdentifier='local.scenesieve.editor',CFBundleVersion=VERSION,CFBundlePackageType='APPL',NSHighResolutionCapable=True),f)
        print('Installed: '+str(app.parent))
    else:
        applications=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications';applications.mkdir(parents=True,exist_ok=True)
        # Desktop Exec uses its own quoting, not shell quoting.
        quoted=str(launcher).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
        (applications/'scenesieve.desktop').write_text('[Desktop Entry]\nType=Application\nName=SceneSieve\nExec="'+quoted+'"\nTerminal=false\nCategories=AudioVideo;Video;\n',encoding='utf-8')
        print('Installed: SceneSieve in your application menu')
    print('Preview release: native desktop playback and scanning still need verification on this OS.',flush=True)
    if '--install-only' not in sys.argv:subprocess.run([str(launcher)],check=True)

if __name__=='__main__':main()
