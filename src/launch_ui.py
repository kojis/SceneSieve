"""Launch modes, media drop targets, and guided scan setup."""
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QPushButton,QWizard,QWizardPage,
    QLineEdit,QHBoxLayout,QFileDialog,QCheckBox,QComboBox,QSizePolicy)
import presets

def media_path(mime):
    from app import VIDEO_EXTENSIONS
    urls=mime.urls() if mime.hasUrls() else []
    if len(urls)!=1 or not urls[0].isLocalFile():return None
    path=Path(urls[0].toLocalFile())
    return str(path) if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS else None

class DropButton(QPushButton):
    dropped=Signal(str)
    def __init__(self,title,copy):
        super().__init__();self.setAcceptDrops(True);self.setMinimumSize(290,260);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setAccessibleName(title+'. '+copy);self.setToolTip('Click to choose this mode, or drop one local video here.')
        self.setStyleSheet('QPushButton{background:#202b36;color:#edf6ff;border:2px dashed #617a90;border-radius:16px;padding:14px;min-height:260px} QPushButton:hover,QPushButton[dragging="true"]{background:#2c4353;border-color:#88dde3} QLabel{background:transparent;border:0}')
        layout=QVBoxLayout(self);layout.setContentsMargins(22,26,22,26);layout.setSpacing(12)
        from glyphs import icon
        graphic=QLabel();graphic.setPixmap(icon('plus').pixmap(36,36));graphic.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(graphic)
        heading=QLabel(title);heading.setStyleSheet('font-size:23px;font-weight:600;background:transparent');heading.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(heading)
        description=QLabel(copy);description.setWordWrap(True);description.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(description,1)
        hint=QLabel('Drop video here or click to choose');hint.setStyleSheet('color:#a9c5d8;background:transparent');hint.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(hint)
        for child in self.findChildren(QLabel):child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    def highlight(self,value):
        self.setProperty('dragging',value);self.style().unpolish(self);self.style().polish(self);self.update()
    def dragLeaveEvent(self,event):self.highlight(False);event.accept()
    def dragEnterEvent(self,event):
        if media_path(event.mimeData()):self.highlight(True);event.acceptProposedAction()
        else:event.ignore()
    def dragMoveEvent(self,event):self.dragEnterEvent(event)
    def dropEvent(self,event):
        path=media_path(event.mimeData());self.highlight(False)
        if path:event.acceptProposedAction();self.dropped.emit(path)
        else:event.ignore()

class LaunchDialog(QDialog):
    def __init__(self,parent):
        super().__init__(None);self.setWindowIcon(parent.windowIcon());self.setStyleSheet(parent.styleSheet());self.choice=None;self.path=None;self.setWindowTitle('Welcome to SceneSieve');self.resize(740,420)
        layout=QVBoxLayout(self);heading=QLabel('Drop your media asset to...');heading.setStyleSheet('font-size:25px;font-weight:600;padding:10px 0');layout.addWidget(heading)
        cards=QHBoxLayout();cards.setSpacing(18);layout.addLayout(cards)
        for title,copy in [('Wizard','allow the wizard to step you through morality augmentation'),('Advanced','Enter an advanced state of [redacted]')]:
            button=DropButton(title,copy);cards.addWidget(button,1)
            button.clicked.connect(lambda checked=False,title=title:self.choose(title,None))
            button.dropped.connect(lambda path,title=title:self.choose(title,path))
        layout.addSpacing(24)
        app_button=QPushButton('Just launch the app...');app_button.clicked.connect(lambda:self.choose('App',None));layout.addWidget(app_button)
    def choose(self,mode,path):self.choice=mode;self.path=path;self.accept()

class MediaPage(QWizardPage):
    def __init__(self,path):
        super().__init__();self.setTitle('Choose your media');self.setSubTitle('Select a local video to review and filter.')
        layout=QVBoxLayout(self);row=QHBoxLayout();layout.addLayout(row)
        self.path=QLineEdit(path or '');self.path.setPlaceholderText('Video file');row.addWidget(self.path)
        browse=QPushButton('Browse…');row.addWidget(browse);browse.clicked.connect(self.browse)
        self.path.textChanged.connect(self.completeChanged)
    def browse(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose video','','Videos (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;All files (*)')
        if path:self.path.setText(path)
    def isComplete(self):
        from app import VIDEO_EXTENSIONS
        path=Path(self.path.text());return path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS

class SetupWizard(QWizard):
    def __init__(self,parent,path=None):
        super().__init__(None);self.setWindowIcon(parent.windowIcon());self.setStyleSheet(parent.styleSheet());self.setWindowTitle('SceneSieve Wizard');self.resize(670,500)
        self.media=MediaPage(path)
        if not self.media.isComplete():self.addPage(self.media)
        page=QWizardPage();page.setTitle('Video filters');page.setSubTitle('Choose what to look for. Leave these empty to skip visual scanning.')
        layout=QVBoxLayout(page);self.categories=[]
        for title,(_,category) in presets.VIDEO.items():
            check=QCheckBox(title);layout.addWidget(check);self.categories.append((check,category))
        self.precise=QCheckBox('Precise detection — verify potential matches');self.precise.setChecked(True);layout.addWidget(self.precise);self.addPage(page)
        page=QWizardPage();page.setTitle('Spoken words');page.setSubTitle('Optional: choose an English preset. Transcription runs if needed.')
        layout=QVBoxLayout(page);self.audio_preset=QComboBox();self.audio_preset.addItem('No spoken-word filtering')
        self.audio_preset.addItems([*presets.AUDIO,'All']);layout.addWidget(self.audio_preset)
        self.treatment=QComboBox();self.treatment.addItem('Mute','duck');self.treatment.addItem('Bleep','bleep');layout.addWidget(self.treatment)
        layout.addWidget(QLabel('Spoken replacement voices and phrases can be configured in the editor.'));self.addPage(page)
        self.setButtonText(QWizard.WizardButton.FinishButton,'Open editor')
    def plan(self):
        return dict(path=self.media.path.text(),categories=', '.join(category for check,category in self.categories if check.isChecked()),words=presets.value(presets.AUDIO,self.audio_preset.currentText()) if self.audio_preset.currentIndex() else '',precise=self.precise.isChecked(),treatment=self.treatment.currentData(),scan=True,audio_preset=self.audio_preset.currentText() if self.audio_preset.currentIndex() else None)

def start_mode(window,mode,path=None,plan=None):
    if mode=='Advanced':
        for name in ('Player','Timeline','Findings','Preview and edit','Detection and export'):window.docks[name].show()
        window.editor_tabs.setCurrentIndex(0);window.docks['Detection and export'].raise_()
    if plan:
        path=plan['path'];window.categories.setText(plan['categories']);window.strict_gore.setChecked(plan['precise'])
        window.audio_panel.set_word_filter(plan.get('audio_preset'),plan['words']);window.audio_panel.mode.setCurrentIndex(window.audio_panel.mode.findData(plan['treatment']))
    if not path:return
    steps=[lambda:window.open_video_path(path)]
    if plan and plan['scan']:
        if plan['categories']:steps.append(window.scan_video)
        if plan['words']:
            steps.append(lambda:window.audio_panel.transcribe() if not window.doc.get('subtitles') else None)
            steps.append(window.audio_panel.find_words)
    window.launch_steps=steps;window.launch_failed=False
    def advance():
        if window.launch_failed or not window.isVisible():return
        if window.job_active:QTimer.singleShot(100,advance);return
        if not window.launch_steps:
            if mode=='Wizard':
                from wizard_guide import ReviewGuide
                window.wizard_guide=ReviewGuide(window);window.wizard_guide.show()
            return
        action=window.launch_steps.pop(0);action()
        if window.job_active:window.worker.failure.connect(lambda _:setattr(window,'launch_failed',True))
        QTimer.singleShot(100,advance)
    QTimer.singleShot(0,advance)
