from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QLineEdit,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QDoubleSpinBox
import subtitle_sources as sources
class SubtitleImport(QDialog):
    def __init__(self,panel):
        super().__init__(panel.w);self.action=None;self.setWindowTitle('Import subtitles');self.setMinimumWidth(410)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('Choose where to import subtitles from:'))
        for title,description,action in [
            ('Open subtitle file…','Import an SRT, VTT, ASS or SSA file.',panel.import_subtitles),
            ('Find matching subtitles…','Search available online subtitle sources.',panel.search_subtitles),
            ('Import from URL…','Download subtitles from a direct HTTPS link.',panel.download),
            ('Use embedded subtitles…','Choose a subtitle track in the loaded video.',panel.embedded)]:
            button=QPushButton(title);button.setToolTip(description);button.clicked.connect(lambda checked=False,action=action:self.choose(action));layout.addWidget(button)
        close=QPushButton('Cancel');close.clicked.connect(self.reject);layout.addWidget(close)
    def choose(self,action):
        self.action=action;self.accept()

class SubtitleSearch(QDialog):
    def __init__(self,panel):
        super().__init__(panel.w);self.panel=panel;self.w=panel.w;self.results=[];self.setWindowTitle('Find matching subtitles');self.resize(1000,540)
        layout=QVBoxLayout(self);row=QHBoxLayout();layout.addLayout(row)
        self.provider=QComboBox();self.provider.addItems(['Internet Archive (no account)','OpenSubtitles (API key)']);row.addWidget(self.provider)
        self.query=QLineEdit(sources.title_guess(self.w.video));row.addWidget(self.query,1)
        self.language=QLineEdit('en');self.language.setMaximumWidth(60);self.language.setToolTip('OpenSubtitles language code, such as en, fr or es. Archive language is shown from item metadata.');row.addWidget(self.language)
        search=QPushButton('Search matches');search.clicked.connect(self.search);row.addWidget(search)
        self.key=QLineEdit(getattr(panel,'subtitle_api_key',''));self.key.setEchoMode(QLineEdit.EchoMode.Password);self.key.setPlaceholderText('OpenSubtitles API key (kept in memory only)');layout.addWidget(self.key)
        self.provider.currentIndexChanged.connect(lambda i:self.key.setVisible(i==1));self.key.hide()
        self.notice=QLabel('Search sends the title and, for OpenSubtitles, a file hash; no video is uploaded.\nInternet Archive provides public downloads; check the displayed uploader rights. OpenSubtitles has account/API limits. Matches may need timing adjustment.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Title / release','Subtitle file','Language','Match','Rights / terms']);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table)
        row=QHBoxLayout();layout.addLayout(row)
        row.addWidget(QLabel('Timing offset'));self.offset=QDoubleSpinBox();self.offset.setRange(-600,600);self.offset.setDecimals(3);self.offset.setSuffix(' s');row.addWidget(self.offset)
        for title,fn in [('View source',self.view),('Download and use selected',self.use),('Close',self.reject)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
    def selected(self):
        row=self.table.currentRow()
        if row<0:raise ValueError('Select a subtitle result first.')
        return self.results[row]
    def view(self):
        try:
            url=QUrl(self.selected()['page'])
            if url.scheme()!='https':raise ValueError('Only HTTPS source links are supported.')
            QDesktopServices.openUrl(url)
        except Exception as e:self.notice.setText(str(e))
    def search(self):
        if self.w.job_active:return
        query=self.query.text().strip();language=self.language.text().strip();key=self.key.text().strip();video=self.w.video;provider=self.provider.currentIndex()
        if not query:self.notice.setText('Enter a title or release name.');return
        if provider==1 and not key:self.notice.setText('Enter your OpenSubtitles API key, or choose Internet Archive.');return
        self.notice.setText('Searching for subtitle files...');self.panel.subtitle_api_key=key
        def done(results):
            self.results=results;self.table.setRowCount(len(results))
            for row,item in enumerate(results):
                for col,k in enumerate(['title','file','language','match','rights']):self.table.setItem(row,col,QTableWidgetItem(str(item.get(k,''))))
            self.table.resizeColumnsToContents();self.notice.setText(f'{len(results)} subtitle files found. Select a result; confirm release/language and review timing.' if results else 'No subtitles found. Try a shorter title, another source, embedded subtitles, or local speech generation.')
        self.w.run_job(lambda p:sources.search_archive(query,language) if provider==0 else sources.search_opensubtitles(video,query,language,key),done)
        self.w.worker.failure.connect(self.notice.setText)
    def use(self):
        if self.w.job_active:return
        try:item=self.selected()
        except Exception as e:self.notice.setText(str(e));return
        duration=self.w.doc['duration'];offset=self.offset.value();key=self.key.text().strip()
        def done(cues):
            adjusted=[{**c,'start':max(0,c['start']+offset),'end':min(duration,c['end']+offset)} for c in cues]
            adjusted=[c for c in adjusted if c['end']>c['start']]
            if not adjusted:self.notice.setText('No cues fit the video with this offset.');return
            self.panel.set_cues(adjusted);self.w.doc['subtitle_source']={k:v for k,v in item.items() if k not in ('url','file_id')};self.accept()
        self.notice.setText('Downloading selected subtitles...');self.w.run_job(lambda p:sources.download(item,duration+abs(offset),key),done);self.w.worker.failure.connect(self.notice.setText)
    def reject(self):
        if self.w.job_active:self.notice.setText('Please wait for the current provider request to finish.');return
        super().reject()
