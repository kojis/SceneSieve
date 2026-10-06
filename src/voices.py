"""Discover installed Windows system voices without blocking the UI."""
import json,os,sys
from pathlib import Path
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QComboBox

class VoiceCombo(QComboBox):
    def __init__(self):
        super().__init__();self.addItem('System default voice','');self.loaded=False
        self.process=QProcess(self);self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(lambda _:self.setToolTip('Voice discovery failed; the System default voice remains available.'))
    def discover(self):
        if self.loaded:return
        self.loaded=True
        if sys.platform=='darwin':self.process.start('/usr/bin/say',['-v','?']);return
        if os.name!='nt':self.process.start('espeak-ng',['--voices']);return
        script="[Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; try { @($s.GetInstalledVoices() | Where-Object {$_.Enabled} | ForEach-Object {$_.VoiceInfo.Name}) | ConvertTo-Json -Compress } finally {$s.Dispose()}"
        self.process.start(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'),['-NoProfile','-NonInteractive','-Command',script])
    def finished(self,*_):
        try:
            output=bytes(self.process.readAllStandardOutput()).decode('utf-8-sig')
            if sys.platform=='darwin':names=[line.split(' #')[0].rsplit(None,1)[0].strip() for line in output.splitlines() if ' #' in line]
            elif os.name!='nt':names=[line.split()[4] for line in output.splitlines()[1:] if len(line.split())>=5]
            else:names=json.loads(output)
            for name in ([names] if isinstance(names,str) else names or []):
                if self.findData(name)<0:self.addItem(name,name)
            self.setToolTip('Installed system speech voices. The selected voice is saved with the replacement.')
        except (ValueError,TypeError):self.setToolTip('No additional system voices were found. The default voice remains available.')
