"""A single filename/folder/type export form."""
from pathlib import Path
import json
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QComboBox,QPushButton,QFileDialog,QMessageBox,QGroupBox
import core,player_exports
from paths import DATA,SETTINGS

class ExportPanel(QWidget):
    def __init__(self,audio):
        super().__init__();self.audio=audio;self.w=audio.w;self.source=None
        layout=QVBoxLayout(self);title=QLabel('Export media');title.setStyleSheet('font-size:18px;font-weight:600');layout.addWidget(title)
        destination_group=QGroupBox('Destination and format');layout.addWidget(destination_group);form=QFormLayout(destination_group);form.setVerticalSpacing(12);form.setHorizontalSpacing(12);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name=QLineEdit();form.addRow('Name',self.name)
        self.folder=QLineEdit(str(self.w.output_dir()));folder_row=QHBoxLayout();folder_row.addWidget(self.folder)
        browse=QPushButton('Browse…');browse.clicked.connect(self.browse);folder_row.addWidget(browse);form.addRow('Save in folder',folder_row)
        self.format=QComboBox()
        for label,kind,ext in [('MP4 video','video','.mp4'),('Matroska video','video','.mkv'),('M4A audio','audio','.m4a'),('WAV audio','audio','.wav'),('FLAC audio','audio','.flac'),('SRT subtitles','subtitles','.srt')]:self.format.addItem(label,(kind,ext))
        for kind,ext in player_exports.FORMATS.items():self.format.addItem(kind,(kind,ext))
        form.addRow('Select file type',self.format)
        self.details=QLabel();self.details.setWordWrap(True);layout.addWidget(self.details)
        self.destination=QLabel();self.destination.setWordWrap(True);layout.addWidget(self.destination)
        self.format.currentIndexChanged.connect(self.change_format);self.name.textChanged.connect(self.update_details);self.folder.textChanged.connect(self.update_details)
        layout.addStretch();buttons=QHBoxLayout();buttons.addStretch();self.export_button=QPushButton('Export');self.export_button.clicked.connect(self.export);buttons.addWidget(self.export_button);layout.addLayout(buttons)
        self.change_format()
    def sync_source(self):
        if self.source!=self.w.video:
            self.source=self.w.video;self.name.setText((Path(self.source).stem if self.source else 'output')+'.filtered'+self.format.currentData()[1]);self.folder.setText(str(self.w.output_dir()))
        self.update_details()
    def browse(self):
        folder=QFileDialog.getExistingDirectory(self,'Export folder',self.folder.text())
        if folder:self.folder.setText(folder)
    def change_format(self):
        name=self.name.text() or 'output.filtered'
        for ext in sorted({'.mp4','.mkv','.m4a','.wav','.flac','.srt',*player_exports.FORMATS.values()},key=len,reverse=True):
            if name.lower().endswith(ext):name=name[:-len(ext)];break
        self.name.setText(name+self.format.currentData()[1]);self.update_details()
    def update_details(self,*_):
        kind,_=self.format.currentData()
        if kind in player_exports.FORMATS:
            text=player_exports.limitation(kind,self.w.doc) if self.w.doc else 'Player sidecar export; compatibility details appear before saving.'
        elif kind=='subtitles':text='Filtered subtitles, with timestamps adjusted for removed scenes.'
        else:text='Applies enabled scene cuts and audio treatments at normal playback speed. '+('Video is encoded as H.264; loaded subtitles are included.' if kind=='video' else 'Exports the first audio track with your filters.')
        self.details.setText(text);self.destination.setText('Destination: '+str(Path(self.folder.text())/self.name.text()))
    def export(self):
        if not self.w.doc:return
        try:
            name=self.name.text().strip();folder=Path(self.folder.text()).expanduser()
            if not name or Path(name).name!=name:raise ValueError('Enter a filename without directory components.')
            if not folder.is_dir():raise ValueError('Choose an existing output folder.')
            kind,ext=self.format.currentData()
            if not name.lower().endswith(ext):name+=ext;self.name.setText(name)
            dest=folder/name
            if dest.resolve()==Path(self.w.video).resolve():raise ValueError('Choose a different name to preserve the original video.')
            conflicts=[p for p in [dest,*([dest.with_suffix('.filtered.srt')] if kind in ('video','audio') and self.w.doc.get('subtitles') else [])] if p.exists()]
            if conflicts and QMessageBox.question(self,'Replace existing output?', '\n'.join(str(p) for p in conflicts)+'\n\nReplace these files?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            self.w.settings['output_dir']=str(folder);DATA.mkdir(parents=True,exist_ok=True);core.atomic_text(SETTINGS,json.dumps(self.w.settings))
            if kind in ('video','audio'):self.audio.export(kind=='audio',str(dest))
            elif kind=='subtitles':self.audio.export_subs(str(dest))
            else:self.w.export(kind,str(dest))
        except Exception as e:self.w.error(str(e))
