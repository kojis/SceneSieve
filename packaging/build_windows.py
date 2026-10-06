"""Build the Windows bootstrap executable with Python's standard library."""
import os,subprocess,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'dist';out.mkdir(exist_ok=True)
archive=out/'app.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted((root/'src').glob('*.py')):
        if not p.name.startswith('test_'):z.write(p,p.name)
    z.write(root/'src/runtime-manifest.json','runtime-manifest.json')
    z.write(root/'src/app.ico','app.ico')
    z.write(root/'docs/Windows-guide.txt','USER_GUIDE.txt')
compiler=Path(os.environ.get('SystemRoot','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if not compiler.exists():raise SystemExit('Windows .NET Framework 4.x C# compiler not found: '+str(compiler))
exe=out/'SceneSieve-Windows-Standalone-v3.25.exe'
subprocess.run([str(compiler),'/nologo','/target:winexe','/out:'+str(exe),'/win32icon:'+str(root/'src/app.ico'),'/resource:'+str(archive)+',app.zip',
    '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.IO.Compression.dll',
    '/reference:System.IO.Compression.FileSystem.dll','/reference:System.Web.Extensions.dll',str(root/'packaging/OnlineLauncher.cs')],check=True)
print(exe)
