"""Speech, subtitle, audio-level and output controls for the main editor."""
import copy,json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QComboBox,QDoubleSpinBox,QCheckBox,QFileDialog,QInputDialog,QGroupBox
import core,media,replacements,presets
from paths import DATA,SETTINGS
class AudioPanel(QWidget):
    def __init__(self,window):
        super().__init__();self.w=window;root=QVBoxLayout(self)
        def section(title):
            group=QGroupBox(title);root.addWidget(group);layout=QVBoxLayout(group);layout.setSpacing(10);return layout
        layout=section('Speech and subtitles')
        row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel('Speech model'))
        self.model=QComboBox();self.model.addItems(['tiny','base','small','medium','large']);self.model.setCurrentText('base');row.addWidget(self.model)
        self.speech_variant=QComboBox();row.addWidget(self.speech_variant)
        self.speech_description=QLabel();self.speech_description.setWordWrap(True)
        self.model.currentTextChanged.connect(self.speech_family_changed);self.speech_family_changed()
        row=QHBoxLayout();layout.addLayout(row)
        self.button(row,'Generate subtitles / detect speech',self.transcribe)
        self.button(row,'Import',self.import_dialog)
        layout.addWidget(self.speech_description)
        layout=section('Word detection')
        row=QHBoxLayout();layout.addLayout(row)
        self.words=QLineEdit();self.words.setPlaceholderText('Words or phrases to filter, separated by commas');row.addWidget(self.words)
        self.selected_word_preset=None
        self.clear_words=self.button(row,'×',self.clear_word_filter);self.clear_words.setAccessibleName('Clear audio preset or custom words');self.clear_words.setToolTip('Clear the filter and enter custom words');self.clear_words.setMinimumWidth(36);self.clear_words.hide()
        self.words.textChanged.connect(self.word_text_changed)
        self.button(row,'Find words',self.find_words)
        self.preset_dropdown=presets.buttons(layout,presets.AUDIO,self.audio_preset)
        preset_note=QLabel('Audio shortcuts use English keyword lists, not context detection. Clear the preset to enter custom words. Review matches; ambiguous terms can produce false positives.');preset_note.setWordWrap(True);layout.addWidget(preset_note)
        layout=section('Word treatment')
        row=QHBoxLayout();layout.addLayout(row)
        self.mode=QComboBox();self.mode.addItem('Mute','duck');self.mode.addItem('Bleep tone','bleep');self.mode.addItem('Spoken replacement','replace');self.mode.addItem('Distort','distort');self.mode.setToolTip('Distort replaces the waveform with noise shaped by its volume, preserving timing and rhythm. Review the result; use Mute for silence.');row.addWidget(QLabel('Word treatment'));row.addWidget(self.mode)
        self.phrase=QComboBox();self.phrase.addItems(['Darn!','Heck!','Oh, shoot!','Good grief!','Oh, bother!','Custom']);self.phrase.setAccessibleName('Spoken replacement phrase');row.addWidget(self.phrase)
        self.custom_phrase=QLineEdit();self.custom_phrase.setMaxLength(120);self.custom_phrase.setPlaceholderText('Type anything to be spoken (up to 120 characters)');self.custom_phrase.setAccessibleName('Custom spoken replacement');layout.addWidget(self.custom_phrase)
        row=QHBoxLayout();layout.addLayout(row)
        from voices import VoiceCombo
        self.voice_label=QLabel('Voice');row.addWidget(self.voice_label);self.voice=VoiceCombo();self.voice.setMaximumWidth(200);row.addWidget(self.voice);self.voice.currentIndexChanged.connect(self.update_apply_state)
        self.frequency=self.spin(row,'Tone',1000,100,4000,' Hz');self.replacement_level=self.spin(row,'Replacement volume',15,0,100,' %')
        self.apply_button=self.button(row,'Apply',self.apply_selected);self.apply_button.setEnabled(False)
        self.phrase.currentTextChanged.connect(self.update_treatment_controls);self.custom_phrase.textChanged.connect(self.update_apply_state);self.frequency.valueChanged.connect(self.update_apply_state);self.replacement_level.valueChanged.connect(self.update_apply_state)
        self.mode.currentIndexChanged.connect(self.update_treatment_controls);self.update_treatment_controls()
        layout=section('Audio levels and normalization')
        row=QHBoxLayout();layout.addLayout(row)
        self.low=self.spin(row,'Quiet below',-40,-65,-5,' dBFS');self.high=self.spin(row,'Loud above',-8,-40,0,' dBFS')
        row=QHBoxLayout();layout.addLayout(row)
        self.target=self.spin(row,'Target RMS',-20,-40,-5,' dBFS')
        row=QHBoxLayout();layout.addLayout(row)
        self.button(row,'Detect audio levels',self.detect_levels)
        self.normalize=QCheckBox('Even out loud/quiet audio');row.addWidget(self.normalize)
        self.normalize.setToolTip('Apply dynamic normalization to filtered playback and exports. Individual detected gains can be disabled in the range list.')
        self.normalize.toggled.connect(self.normalize_changed)
        from export_ui import ExportPanel
        self.export_panel=ExportPanel(self)
        self.info=QLabel('Speech is processed locally. Models download on first use. Subtitle matches with sentence-level timing require boundary review.\nAudio filters use the first audio track. Export keeps the first video/audio tracks and replaces subtitles with the filtered transcript.');self.info.setWordWrap(True);root.addWidget(self.info);root.addStretch()
    def button(self,row,text,fn):
        b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b);return b
    def spin(self,row,label,value,low,high,suffix):
        caption=QLabel(label);row.addWidget(caption);s=QDoubleSpinBox();s.caption=caption;s.setRange(low,high);s.setValue(value);s.setSuffix(suffix);row.addWidget(s);return s
    def normalize_changed(self,value):
        if self.w.doc:self.w.doc['normalize_audio']=value;self.w.dirty=True;self.w.update_summary()
    def job(self,fn,done):
        self.w.cancel.clear();self.w.run_job(fn,done,True)
    def set_cues(self,cues):
        self.w.doc['subtitles']=cues;self.w.dirty=True;self.info.setText(f'{len(cues)} subtitle entries loaded. Find words to add audio-filter ranges.');self.w.status.setText('Subtitles loaded.');self.w.update_summary()
    def speech_family_changed(self,*_):
        family=self.model.currentText();self.speech_variant.clear()
        variants=['large-v2','large-v3','large-v3-turbo'] if family=='large' else [family,family+'.en']
        for name in variants:self.speech_variant.addItem(name+(' (English)' if name.endswith('.en') else ' (multilingual)'),name)
        self.speech_description.setText({'tiny':'Fastest/lightest speech option; more transcription errors expected.','base':'Lightweight speech model; useful starting point for CPU transcription.','small':'More capacity than base; increased memory and transcription time.','medium':'Larger speech model; slower on CPU. Check word boundaries.','large':'Highest-capacity Whisper family here; substantial CPU/memory cost. Turbo trades some capacity for speed.'}[family]+' Quality depends on language, noise and dialogue.')
    def transcribe(self):
        video=self.w.video;model=self.speech_variant.currentData();self.job(lambda p:media.transcribe(video,model,p,self.w.cancel),self.set_cues)
    def import_dialog(self):
        if not self.w.doc:return
        from subtitle_ui import SubtitleImport
        dialog=SubtitleImport(self)
        if dialog.exec() and dialog.action:dialog.action()
    def import_subtitles(self):
        path,_=QFileDialog.getOpenFileName(self,'Import subtitles','','Subtitles (*.srt *.vtt *.ass *.ssa)')
        if path:
            try:self.set_cues(media.read_subtitles(path,self.w.doc['duration']))
            except Exception as e:self.w.error(str(e))
    def embedded(self):
        try:
            streams=[s for s in media.probe(self.w.video) if s['codec_type']=='subtitle']
            if not streams:raise ValueError('No embedded subtitles. Import, download, or generate subtitles instead.')
            names=[f"{s['index']}: {s.get('tags',{}).get('language','unknown')} ({s.get('codec_name','')})" for s in streams]
            item,ok=QInputDialog.getItem(self,'Subtitle track','Choose a text subtitle track',names,0,False)
            if ok:
                index=streams[names.index(item)]['index'];video=self.w.video;duration=self.w.doc['duration']
                self.job(lambda p:media.embedded_subtitles(video,index,p,self.w.cancel,duration),self.set_cues)
        except Exception as e:self.w.error(str(e))
    def search_subtitles(self):
        from subtitle_ui import SubtitleSearch
        self.search_dialog=SubtitleSearch(self);self.search_dialog.exec()
    def download(self):
        url,ok=QInputDialog.getText(self,'Download subtitles','HTTPS URL of an SRT, VTT or ASS subtitle file:')
        if ok and url:
            duration=self.w.doc['duration'];self.job(lambda p:media.download_subtitles(url.strip(),duration),self.set_cues)
    def set_word_filter(self,name=None,custom=''):
        self.selected_word_preset=name if name in presets.AUDIO or name=='All' else None
        self.words.setReadOnly(bool(self.selected_word_preset))
        self.words.setText(self.selected_word_preset or custom)
        self.clear_words.setVisible(bool(self.words.text()))
    def word_terms(self):
        return presets.value(presets.AUDIO,self.selected_word_preset) if self.selected_word_preset else self.words.text()
    def word_text_changed(self,text):
        if self.selected_word_preset and text!=self.selected_word_preset:
            self.selected_word_preset=None;self.words.setReadOnly(False)
        self.clear_words.setVisible(bool(text))
    def clear_word_filter(self):
        self.set_word_filter();self.preset_dropdown.setCurrentIndex(0);self.words.setFocus()
    def audio_preset(self,name):
        if not self.w.doc or (self.w.job_active):return
        self.set_word_filter(name)
        if self.w.doc.get('subtitles'):self.find_words();return
        if self.mode.currentData()=='replace' and not self.replacement_text():
            self.w.error('Enter the custom phrase to speak before scanning.');return
        video=self.w.video;duration=self.w.doc['duration'];model=self.speech_variant.currentData();terms=self.word_terms();amount=0
        treatment=dict(action=self.mode.currentData(),level=amount/100,replacement=self.replacement_text(),frequency=self.frequency.value(),voice=self.voice.currentData() or '',replacement_level=self.replacement_level.value()/100)
        def scan(progress):
            cues=media.transcribe(video,model,progress,self.w.cancel)
            if self.w.cancel.is_set():raise InterruptedError('Audio scan cancelled.')
            scenes=[{**s,**treatment} for s in media.word_scenes(cues,terms,duration,amount)]
            core.validate({'version':1,'duration':duration,'scenes':scenes})
            return cues,replacements.prepare_all(scenes,progress,self.w.cancel)
        def done(result):
            cues,scenes=result;self.w.doc['subtitles']=cues
            self.w.doc['scenes']=[s for s in self.w.doc['scenes'] if s.get('source')!='speech-search']+scenes
            self.w.dirty=True;self.w.refresh()
            self.w.docks['Findings'].show();self.w.docks['Findings'].raise_()
            self.w.status.setText(f'{len(scenes)} word matches added from {name}. Review timing and context.')
        self.job(scan,done)
    def find_words(self):
        try:
            cues=self.w.doc.get('subtitles',[])
            if not cues:raise ValueError('Generate, import, or download subtitles first.')
            scenes=media.word_scenes(cues,self.word_terms(),self.w.doc['duration'],0)
            scenes=[self.treatment(s) for s in scenes]
            def done(prepared):
                self.w.doc['scenes']=[s for s in self.w.doc['scenes'] if s.get('source')!='speech-search']+prepared
                self.w.dirty=True;self.w.refresh();self.w.status.setText(f'{len(prepared)} word matches added. Review timing and replacement audio.')
            self.job(lambda p:replacements.prepare_all(scenes,p,self.w.cancel),done)
        except Exception as e:self.w.error(str(e))
    def replacement_text(self):
        return (self.custom_phrase.text() if self.phrase.currentText()=='Custom' else self.phrase.currentText()).strip()
    def update_treatment_controls(self):
        mode=self.mode.currentData()
        self.phrase.setVisible(mode=='replace')
        self.custom_phrase.setVisible(mode=='replace' and self.phrase.currentText()=='Custom')
        self.frequency.setVisible(mode=='bleep');self.frequency.caption.setVisible(mode=='bleep')
        self.voice.setVisible(mode=='replace');self.voice_label.setVisible(mode=='replace')
        self.replacement_level.setVisible(mode in ('bleep','replace'));self.replacement_level.caption.setVisible(mode in ('bleep','replace'))
        if mode=='replace':self.voice.discover()
        self.update_apply_state()
    def update_apply_state(self,*_):
        if not hasattr(self,'apply_button'):return
        rows=self.w.selected_rows() if self.w.doc else []
        keys=['action']
        mode=self.mode.currentData()
        keys+=['level'] if mode=='duck' else [] if mode=='distort' else ['replacement_level','frequency' if mode=='bleep' else 'replacement']
        if mode=='replace':keys.append('voice')
        changed=False
        for row in rows:
            scene=self.w.doc['scenes'][row]
            if scene.get('action') not in ('duck','bleep','replace','distort'):continue
            target=dict(action=mode,level=0,replacement=self.replacement_text(),frequency=self.frequency.value(),voice=self.voice.currentData() or '',replacement_level=self.replacement_level.value()/100)
            defaults=dict(level=0,replacement='Darn!',frequency=1000,voice='',replacement_level=.15)
            changed|=any(scene.get(k,defaults.get(k))!=target[k] for k in keys)
        self.apply_button.setEnabled(changed and (mode!='replace' or bool(self.replacement_text())))
    def treatment(self,scene):
        updated={**scene,'action':self.mode.currentData(),'level':0/100,'replacement':self.replacement_text(),'frequency':self.frequency.value(),'voice':self.voice.currentData() or '','replacement_level':self.replacement_level.value()/100}
        core.validate({'version':1,'duration':self.w.doc['duration'],'scenes':[updated]})
        return updated
    def apply_selected(self):
        if not self.apply_button.isEnabled():return
        try:
            rows=[r for r in self.w.selected_rows() if self.w.doc['scenes'][r]['action'] in ('duck','bleep','replace','distort')]
            if not rows:raise ValueError('Select word/audio-replacement ranges in the range list first.')
            scenes=[self.treatment(self.w.doc['scenes'][r]) for r in rows]
            def done(prepared):
                for row,scene in zip(rows,prepared):self.w.doc['scenes'][row]=scene
                self.w.dirty=True;self.w.refresh();self.w.status.setText('Updated selected word treatments. Select Filtered to hear the changes.');self.update_apply_state()
            self.job(lambda p:replacements.prepare_all(scenes,p,self.w.cancel),done)
        except Exception as e:self.w.error(str(e))
    def load_words(self):
        p,_=QFileDialog.getOpenFileName(self,'Load word list','','Text (*.txt)')
        if p:self.words.setText(', '.join(Path(p).read_text(encoding='utf-8-sig').splitlines()))
    def save_words(self):
        p,_=QFileDialog.getSaveFileName(self,'Save word list',str(self.w.output_dir()/'words.txt'),'Text (*.txt)')
        if p:core.atomic_text(p,'\n'.join(t.strip() for t in self.words.text().split(',') if t.strip()))
    def detect_levels(self):
        def apply(wave):
            self.w.waveform.data=wave;self.w.waveform.update()
            scenes=media.level_scenes(wave,self.w.doc['duration'],low,high,target)
            self.w.doc['scenes']=[s for s in self.w.doc['scenes'] if s.get('source')!='audio-level']+scenes
            self.w.dirty=True;self.w.refresh();self.w.status.setText(f'{len(scenes)} audio-level ranges added with suggested gain adjustments.')
        low,high,target=self.low.value(),self.high.value(),self.target.value()
        if low>=high:self.w.error('Quiet threshold must be below loud threshold.');return
        video=self.w.video
        if self.w.waveform.data['rms']:apply(self.w.waveform.data)
        else:self.job(lambda p:media.waveform(video,p,self.w.cancel),apply)
    def export(self,audio,path=None):
        if not path:path,_=QFileDialog.getSaveFileName(self,'Export filtered audio' if audio else 'Export filtered video',str(self.w.output_dir()/(Path(self.w.video).stem+('.filtered.m4a' if audio else '.filtered.mp4'))),'Audio (*.m4a *.wav *.flac)' if audio else 'Video (*.mp4 *.mkv)')
        if not path:return
        if Path(path).suffix.lower() not in (('.m4a','.wav','.flac') if audio else ('.mp4','.mkv')):self.w.error('Choose a supported output extension.');return
        doc=copy.deepcopy(self.w.doc);video=self.w.video;labels=self.w.labels();padding=self.w.padding.value();normalize=self.normalize.isChecked()
        self.job(lambda p:media.export_media(video,doc,path,labels,padding,normalize,p,self.w.cancel,audio),lambda p:self.w.status.setText('Exported '+p))
    def export_subs(self,path=None):
        if not path:path,_=QFileDialog.getSaveFileName(self,'Export filtered subtitles',str(self.w.output_dir()/(Path(self.w.video).stem+'.filtered.srt')),'Subtitles (*.srt)')
        if path:
            try:
                kept=core.kept_ranges(self.w.doc['duration'],core.cuts(self.w.doc,self.w.labels(),self.w.padding.value()))
                core.atomic_text(path,media.subtitle_text(self.w.doc,kept));self.w.status.setText('Exported '+path)
            except Exception as e:self.w.error(str(e))
