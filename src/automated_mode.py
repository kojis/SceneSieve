"""Progress-only automated scan, followed by export and application shutdown."""
import threading
from pathlib import Path
from PySide6.QtCore import QObject,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QPushButton,QFileDialog,QMessageBox
import core,media,scanner,presets,models,local_ai,player_exports
from paths import DATA
from app import Worker
from scan_progress import ScanProgress

AUTO_PADDING=1.0

def automatic_categories():
    return [value for name,(_,value) in presets.VIDEO.items() if name!='Insects and Spiders']

def process(video,model,progress,cancel):
    progress('Loading media 0/3 - reading video information')
    duration=scanner.probe(video);progress(f'Media duration: {duration:.3f}s')
    if cancel.is_set():raise InterruptedError('Cancelled.')
    progress('Loading media 1/3 - identifying media')
    identity=core.fingerprint(video)
    progress('Loading media 2/3 - starting local models')
    local_ai.start();models.ensure_model(model,progress,cancel)
    categories=automatic_categories()
    scenes=scanner.scan(video,duration,model,categories,.5,cancel,progress,cache_dir=DATA/'scan-cache',identity=identity,precision=0)
    cues=[]
    if any(s['codec_type']=='audio' for s in media.probe(video)):
        cues=media.transcribe(video,'small',progress,cancel)
        scenes.extend({**s,'action':'skip'} for s in media.word_scenes(cues,presets.value(presets.AUDIO,'All'),duration,0))
    if cancel.is_set():raise InterruptedError('Cancelled.')
    doc=dict(version=1,video=Path(video).name,duration=duration,fingerprint=identity,scenes=scenes,subtitles=cues,
             automatic_settings=dict(categories=categories,audio_presets=list(presets.AUDIO),precision=0,interval=.5,padding=AUTO_PADDING))
    core.validate(doc);progress('Automatic scan complete. Choose export options.')
    return doc

def export_result(video,doc,path,kind,progress,cancel):
    if cancel.is_set():raise InterruptedError('Cancelled.')
    if kind in ('video','audio'):
        return media.export_media(video,doc,path,None,AUTO_PADDING,False,progress,cancel,kind=='audio')
    if kind=='json':core.save(path,doc)
    elif kind=='subtitles':
        kept=core.kept_ranges(doc['duration'],core.cuts(doc,None,AUTO_PADDING));core.atomic_text(path,media.subtitle_text(doc,kept))
    else:core.atomic_text(path,player_exports.export_text(kind,video,doc,None,AUTO_PADDING))
    return str(path)

class AutomatedExport(QDialog):
    def __init__(self,controller):
        super().__init__(None);self.c=controller;self.setWindowIcon(controller.icon);self.setStyleSheet(controller.style);self.setWindowTitle('Export automatic edit');self.resize(660,440)
        layout=QVBoxLayout(self);count=len(controller.doc['scenes'])
        summary=QLabel(f'Automatic scan finished: {count} matching ranges. Choose one export. The app closes after it finishes.');summary.setWordWrap(True);layout.addWidget(summary)
        note=QLabel('Broad filtering may remove harmless scenes and can still miss unsuitable content. Spoken-word shortcuts use English keywords. Insects and Spiders were excluded.');note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();form.setVerticalSpacing(12);layout.addLayout(form)
        self.folder=QLineEdit(controller.folder);row=QHBoxLayout();row.addWidget(self.folder);browse=QPushButton('Browse…');row.addWidget(browse);browse.clicked.connect(self.browse);form.addRow('Output folder',row)
        self.name=QLineEdit(Path(controller.video).stem+'.filtered.mp4');form.addRow('Filename',self.name)
        self.format=QComboBox()
        for label,kind,ext in [('MP4 video','video','.mp4'),('Matroska video','video','.mkv'),('M4A audio','audio','.m4a'),('WAV audio','audio','.wav'),('FLAC audio','audio','.flac'),('Scene data JSON','json','.scenes.json'),('Filtered subtitles','subtitles','.srt')]:self.format.addItem(label,(kind,ext))
        for kind,ext in player_exports.FORMATS.items():self.format.addItem(kind,(kind,ext))
        form.addRow('Format',self.format);self.format.currentIndexChanged.connect(self.change_format)
        self.details=QLabel('Exports the filtered media with matching scenes removed.');self.details.setWordWrap(True);layout.addWidget(self.details)
        layout.addStretch();buttons=QHBoxLayout();layout.addLayout(buttons);close=QPushButton('Cancel and close');close.clicked.connect(self.reject);buttons.addWidget(close);export=QPushButton('Export and close');export.clicked.connect(self.export);buttons.addWidget(export)
    def browse(self):
        folder=QFileDialog.getExistingDirectory(self,'Output folder',self.folder.text())
        if folder:self.folder.setText(folder)
    def change_format(self):
        kind,ext=self.format.currentData();name=self.name.text()
        for suffix in sorted({self.format.itemData(i)[1] for i in range(self.format.count())},key=len,reverse=True):
            if name.lower().endswith(suffix):name=name[:-len(suffix)];break
        self.name.setText(name+ext)
        self.details.setText(player_exports.limitation(kind,self.c.doc) if kind in player_exports.FORMATS else 'Exports the automatic edit. Scene JSON preserves the original source timestamps; its automatic_settings records the padding used.')
    def export(self):
        try:
            name=self.name.text().strip();folder=Path(self.folder.text()).expanduser();kind,ext=self.format.currentData()
            if not name or Path(name).name!=name:raise ValueError('Enter a filename without folders.')
            if not folder.is_dir():raise ValueError('Choose an existing output folder.')
            if not name.lower().endswith(ext):name+=ext;self.name.setText(name)
            path=folder/name
            if path.resolve()==Path(self.c.video).resolve():raise ValueError('Choose a different output name to preserve the source.')
            conflicts=[p for p in (path,path.with_suffix('.filtered.srt')) if p.exists()]
            if conflicts and QMessageBox.question(self,'Replace output?', '\n'.join(map(str,conflicts)),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            if kind in player_exports.FORMATS and QMessageBox.warning(self,'Export compatibility',player_exports.limitation(kind,self.c.doc)+'\n\nContinue?',QMessageBox.StandardButton.Ok|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Ok:return
            self.hide();self.c.run(lambda progress:export_result(self.c.video,self.c.doc,path,kind,progress,self.c.cancel),lambda _:self.c.finish(),self.c.doc['duration'],retry_export=True)
        except Exception as e:QMessageBox.warning(self,'Export options',str(e))
    def reject(self):super().reject();self.c.finish()

class AutomatedMode(QObject):
    def __init__(self,application,window,video):
        super().__init__(application);self.application=application;self.video=video;self.model=window.selected_model() or 'gemma3:4b';self.icon=window.windowIcon();self.style=window.styleSheet();self.folder=str(window.settings.get('output_dir',Path(video).parent));self.doc=None;self.cancel=threading.Event();self.worker=None;self.export_dialog=None;self.progress=None
    def start(self):self.run(lambda p:process(self.video,self.model,p,self.cancel),self.scanned)
    def run(self,fn,done,duration=0,retry_export=False):
        self.cancel.clear();self.result=None;self.failure=None
        self.progress=ScanProgress(None,self.cancel.set,duration);self.progress.setWindowIcon(self.icon);self.progress.setStyleSheet(self.style);self.progress.setWindowTitle('Automatic filtering');self.progress.show()
        self.worker=Worker(fn);self.worker.progress.connect(self.progress.update_progress)
        self.worker.result.connect(lambda value:setattr(self,'result',value));self.worker.failure.connect(lambda value:setattr(self,'failure',value))
        def completed():
            worker=self.worker;self.worker=None;worker.deleteLater()
            if self.cancel.is_set():self.progress.done(0);self.finish();return
            if self.failure:
                self.progress.stage.setText('Operation stopped');self.progress.detail.setText(self.failure+'\nNo completed export was produced.');self.progress.cancel_button.clicked.disconnect()
                if retry_export:
                    self.progress.cancel_job=self.back_to_export;self.progress.cancel_button.setText('Back to export options');self.progress.cancel_button.clicked.connect(self.back_to_export)
                else:
                    self.progress.cancel_job=self.finish;self.progress.cancel_button.setText('Close');self.progress.cancel_button.clicked.connect(self.finish)
                self.progress.cancel_button.setEnabled(True);return
            self.progress.done(0);self.progress.deleteLater();self.progress=None;done(self.result)
        self.worker.finished.connect(completed);self.worker.start()
    def back_to_export(self):
        self.progress.done(0);self.progress.deleteLater();self.progress=None;self.export_dialog.show()
    def scanned(self,doc):self.doc=doc;self.export_dialog=AutomatedExport(self);self.export_dialog.show()
    def finish(self):
        if self.worker:self.cancel.set();return
        self.application.quit()
