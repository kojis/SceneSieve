from __future__ import annotations
import json
import copy
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import cv2
from PySide6.QtCore import Qt, QThread, Signal, QProcess, QTimer
from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QLineEdit, QDoubleSpinBox, QComboBox, QHeaderView, QAbstractItemView, QSplitter,
    QDialog, QFormLayout, QDialogButtonBox, QCheckBox, QTabWidget, QSlider, QProgressBar, QScrollArea, QInputDialog)
import core
import scanner
from player import EmbeddedPlayer, playback_time
from timeline import Timeline
from video_controls import VideoOverlay, SubtitleSidebar, PlaybackToggle
from PySide6.QtCore import QItemSelectionModel
from glyphs import set_glyph
from PySide6.QtWidgets import QStyle,QGroupBox

from paths import ROOT, DATA, BIN, SETTINGS
import models as model_catalog
import media
import replacements
import player_exports
import presets
import visual_effects
from audio_ui import AudioPanel
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.mpg',
                    '.mpeg', '.wmv', '.flv', '.ts', '.mts', '.m2ts', '.vob', '.ogv', '.3gp'}

class Worker(QThread):
    result = Signal(object)
    failure = Signal(str)
    progress = Signal(str)
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
    def run(self):
        try:
            self.result.emit(self.fn(self.progress.emit))
        except Exception as e:
            self.failure.emit(str(e))

class SceneDialog(QDialog):
    def __init__(self, parent, duration, scene=None):
        super().__init__(parent)
        self.setWindowTitle('Edit scene' if scene else 'Mark a scene')
        self.duration = duration
        scene = scene or {'start':0,'end':min(5,duration),'category':'gore','enabled':True,'reviewed':True}
        self.original = dict(scene)
        form = QFormLayout(self)
        self.start = QLineEdit(core.clock(scene['start']))
        self.end = QLineEdit(core.clock(scene['end']))
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(['gore','blood','violence','other'])
        self.category.setCurrentText(scene['category'])
        from visual_effects import OPTIONS
        self.action=QComboBox()
        for label,value in (*OPTIONS,('Mute / duck','duck'),('Gain','gain'),('Bleep','bleep'),('Spoken replacement','replace'),('Distort','distort')):self.action.addItem(label,value)
        self.action.setCurrentIndex(self.action.findData(scene.get('action','skip')))
        self.audio_level=QDoubleSpinBox();self.audio_level.setRange(0,100);self.audio_level.setValue(scene.get('level',0)*100);self.audio_level.setSuffix(' % remaining')
        self.gain=QDoubleSpinBox();self.gain.setRange(-60,24);self.gain.setValue(scene.get('gain_db',0));self.gain.setSuffix(' dB')
        form.addRow('Action',self.action);form.addRow('Word audio',self.audio_level);form.addRow('Audio gain',self.gain)
        self.replacement=QLineEdit(scene.get('replacement','Darn!'));form.addRow('Spoken substitute',self.replacement)
        self.frequency=QDoubleSpinBox();self.frequency.setRange(100,4000);self.frequency.setValue(scene.get('frequency',1000));self.frequency.setSuffix(' Hz');form.addRow('Bleep tone',self.frequency)
        self.replacement_level=QDoubleSpinBox();self.replacement_level.setRange(0,100);self.replacement_level.setValue(scene.get('replacement_level',.15)*100);self.replacement_level.setSuffix(' %');form.addRow('Replacement volume',self.replacement_level)
        from voices import VoiceCombo
        self.voice=VoiceCombo()
        if scene.get('voice'):self.voice.addItem(scene['voice'],scene['voice']);self.voice.setCurrentIndex(1)
        form.addRow('Voice',self.voice)
        def treatment_visibility():
            mode=self.action.currentData()
            for field,visible in [(self.audio_level,mode=='duck'),(self.gain,mode=='gain'),(self.frequency,mode=='bleep'),(self.voice,mode=='replace'),(self.replacement,mode=='replace'),(self.replacement_level,mode in ('bleep','replace'))]:
                field.setVisible(visible);form.labelForField(field).setVisible(visible)
            if mode=='replace':self.voice.discover()
        self.action.currentTextChanged.connect(treatment_visibility);treatment_visibility()
        self.enabled = QCheckBox('Include in filters')
        self.enabled.setChecked(scene['enabled'])
        self.reviewed = QCheckBox('I have checked these boundaries')
        self.reviewed.setChecked(scene['reviewed'])
        for label, widget in [('Start',self.start),('End',self.end),('Category',self.category),('',self.enabled),('',self.reviewed)]:
            form.addRow(label,widget)
        form.addRow(QLabel('Times refer to the original video. Use HH:MM:SS.mmm or seconds.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
    def validate(self):
        try:
            a,b = core.timestamp(self.start.text()),core.timestamp(self.end.text())
            category = self.category.currentText().strip()
            if not 0 <= a < b <= self.duration or not category:
                raise ValueError('Choose a category and valid start/end times within the video.')
            self.value = {**self.original,'start':a,'end':b,'category':category,'enabled':self.enabled.isChecked(),
                          'reviewed':self.reviewed.isChecked(),'action':self.action.currentData(),'level':self.audio_level.value()/100,'gain_db':self.gain.value(),'replacement':self.replacement.text().strip(),'voice':self.voice.currentData() or '','frequency':self.frequency.value(),'replacement_level':self.replacement_level.value()/100,'source':'manual'}
            core.validate({'version':1,'duration':self.duration,'scenes':[self.value]})
            self.accept()
        except Exception as e:
            QMessageBox.warning(self,'Check scene',str(e))

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('SceneSieve • Local video filters')
        from glyphs import icon
        self.setWindowIcon(icon('eye'))
        screen=QApplication.primaryScreen().availableGeometry();self.resize(min(1280,screen.width()),min(940,screen.height()-40))
        try:self.settings=json.loads(SETTINGS.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.settings={}
        self.video = None
        self.doc = None
        self.dirty = False
        self.worker = None
        self.job_active = False
        self.cancel = threading.Event()
        self.temp = tempfile.TemporaryDirectory(prefix='scenesieve-')
        self.players = []
        self.jobs = 0
        self.source_position=0.;self.mark_start=None;self.mark_end=None;self.playback_mode='original'
        self.reload_timer=QTimer(self);self.reload_timer.setSingleShot(True);self.reload_timer.setInterval(180)
        self.reload_timer.timeout.connect(lambda:self.load_embedded(paused=True,preview=getattr(self,'preview_bounds',None) if self.playback_mode=='preview' else None))
        self.setStyleSheet('''QMainWindow,QDialog{background:#101820;color:#e8edf2} QWidget{font-size:13px;color:#e8edf2;background:#101820} QTabBar::tab{background:#263a48;padding:7px} QTabBar::tab:selected{background:#34556a} QProgressBar{background:#19252e;border:1px solid #395463} QProgressBar::chunk{background:#62b9c8}
            QPushButton{background:#263a48;border:1px solid #395463;padding:9px 14px;border-radius:5px}
            QPushButton:hover{background:#34556a} QPushButton:disabled{color:#72818b;background:#19252e}
            QLineEdit,QComboBox,QDoubleSpinBox,QTableWidget{background:#182630;border:1px solid #344a58;padding:5px}
            QHeaderView::section{background:#223743;padding:8px;border:0} QTableWidget::item:selected{background:#34596b}
            QLabel#title{font-size:28px;font-weight:700} QLabel#muted{color:#a9bcc8}''')
        self.setStyleSheet(self.styleSheet()+'''
            QMainWindow,QDialog,QWidget{background:#171a20;color:#dce2eb;font-family:"Segoe UI";font-size:12px}
            QPushButton{background:#282e38;border:1px solid #3a4350;padding:7px 12px;min-height:1.5em;border-radius:4px}
            QPushButton:hover{background:#354251;border-color:#7399b5}
            QPushButton:pressed{background:#42637a}
            QLineEdit,QComboBox,QDoubleSpinBox,QTableWidget{background:#1e232b;border:1px solid #363f4d;padding:4px;selection-background-color:#375972}
            QLineEdit,QComboBox,QDoubleSpinBox,QSpinBox{min-height:1.5em;padding-top:6px;padding-bottom:6px}
            QCheckBox,QRadioButton{min-height:1.5em;padding-top:3px;padding-bottom:3px}
            QHeaderView::section{background:#252c36;color:#9baabd;padding:6px;border:0}
            QTabBar::tab{background:#20262f;color:#a7b4c6;padding:8px 16px;border-bottom:2px solid transparent}
            QTabBar::tab:selected{background:#29333f;color:#edf5ff;border-bottom:2px solid #73bcd9}
            QSplitter::handle{background:#303845}
            QGroupBox{border:1px solid #394554;border-radius:5px;margin-top:1.6em;padding:12px 10px 10px 10px} QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 5px;color:#b4cedd}
            QScrollArea{border:0}
            QScrollBar:vertical{background:#1e232b;width:10px}
            QScrollBar::handle:vertical{background:#495464;min-height:20px;border-radius:4px}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
            QSlider::groove:vertical{background:#303b48;width:4px;border-radius:2px}
            QSlider::handle:vertical{background:#b2d9e8;border:1px solid #17252d;height:12px;margin:0 -4px;border-radius:3px}
        ''')
        base = QWidget(); self.setCentralWidget(base)
        layout = QVBoxLayout(base); layout.setContentsMargins(16,12,16,12); layout.setSpacing(8)
        title = QLabel('SceneSieve'); title.setObjectName('title'); layout.addWidget(title)
        subtitle = QLabel('Your video. Your boundaries.  •  Files stay on this computer.'); subtitle.setObjectName('muted'); layout.addWidget(subtitle)
        title.hide();subtitle.hide()
        toolbar = QHBoxLayout(); layout.addLayout(toolbar)
        self.buttons=[]
        def button(text,fn,row=toolbar):
            b=QPushButton(text); b.clicked.connect(fn); row.addWidget(b); self.buttons.append(b)
            media_icons={'Play':('play','Play (Space)'), 'Play / pause':('play','Play / pause (Space)'), '◀ Frame':('frame-back','Previous frame (Left / comma)'), 'Frame ▶':('frame-next','Next frame (Right / period)'), 'Previous mark':('previous','Previous mark ([)'), 'Next mark':('next','Next mark (])'), '−':('minus','Zoom out (-)'), '+':('plus','Zoom in (+)'), 'Fit':('fit','Fit timeline (Ctrl+0)')}
            if text in media_icons:set_glyph(b,*media_icons[text]);b.setMinimumSize(38,32)
            file_icons={'Open video':'SP_DialogOpenButton','Load scenes':'SP_FileDialogContentsView','Save scenes':'SP_DialogSaveButton','Output folder…':'SP_DirIcon','Remove selected':'SP_TrashIcon','Edit selected':'SP_FileDialogDetailedView'}
            if text in file_icons:b.setIcon(self.style().standardIcon(getattr(QStyle.StandardPixmap,file_icons[text])))
            if text in ('Add scene','Add selected range'):set_glyph(b,'plus',text,only=False)
            return b
        button('Open video',self.open_video)
        button('Load scenes',self.load_scenes)
        button('Save scenes',self.save_scenes)
        toolbar.addStretch()
        self.output_label=QLabel(self.settings.get('output_dir','Output: choose a folder or save beside the source video'))
        self.output_label.hide()
        self.file_label=QLabel('Drop a video anywhere in this window, or choose Open video.'); layout.addWidget(self.file_label)
        self.file_label.setToolTip('Drop one local video at a time. Its matching scene file loads automatically.')
        self.content=QWidget(); content=QVBoxLayout(self.content); content.setContentsMargins(0,0,0,0);layout.addWidget(self.content)
        content.setSpacing(8)
        self.workspace_splitter=QSplitter(Qt.Orientation.Vertical)
        content.addWidget(self.workspace_splitter)
        playback_panel=QWidget();content=QVBoxLayout(playback_panel);content.setContentsMargins(0,0,0,0)
        self.workspace_splitter.addWidget(playback_panel)
        self.surface=QWidget();self.surface.setMinimumHeight(180);self.surface.setStyleSheet('background:black')
        if sys.platform=='darwin':
            hint=QLabel('Video plays in the separate SceneSieve Preview window on macOS.\nUse the controls below to play, seek, and switch filters.',self.surface);hint.setWordWrap(True);hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            QVBoxLayout(self.surface).addWidget(hint)
        self.surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow);self.surface.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.video_splitter=QSplitter(Qt.Orientation.Horizontal)
        self.video_splitter.addWidget(self.surface)
        self.subtitle_sidebar=SubtitleSidebar(self.seek_subtitle)
        self.video_splitter.addWidget(self.subtitle_sidebar);self.video_splitter.setStretchFactor(0,3);self.video_splitter.setStretchFactor(1,1)
        content.addWidget(self.video_splitter,2)
        self.video_overlay=VideoOverlay(self)
        self.embedded=EmbeddedPlayer(self.surface,self)
        self.embedded.positionChanged.connect(self.position_changed)
        self.embedded.pausedChanged.connect(self.update_play_glyphs)
        self.embedded.pausedChanged.connect(self.video_overlay.paused)
        self.embedded.failed.connect(self.error)
        self.embedded.keyPressed.connect(self.player_key)
        self.embedded.loaded.connect(self.apply_audio)
        self.embedded.seekSettled.connect(self.audio_seek_settled)
        transport=QHBoxLayout();content.addLayout(transport)
        self.play_button=button('Play',self.play,transport)
        self.play_button.setStyleSheet('QPushButton{background:#345b70;border:1px solid #6090a6;font-weight:600} QPushButton:hover{background:#416f87}')
        button('◀ Frame',lambda:self.jog_frame(-1),transport);button('Frame ▶',lambda:self.jog_frame(1),transport)
        button('Previous mark',lambda:self.jump_mark(-1),transport);button('Next mark',lambda:self.jump_mark(1),transport)
        self.filtered=PlaybackToggle()
        self.filtered.toggled.connect(lambda _:self.load_embedded(paused=self.embedded.paused,preview=getattr(self,'preview_bounds',None) if self.playback_mode=='preview' else None))
        self.speed=QComboBox();self.speed.setToolTip('Playback speed')
        for rate in (.25,.5,.75,1.,1.25,1.5,1.75,2.,3.):self.speed.addItem(f'{rate:g}×',rate)
        self.speed.setCurrentIndex(3);self.speed.currentIndexChanged.connect(lambda:self.embedded.command('set_property','speed',self.speed.currentData()));transport.addWidget(self.speed)
        self.time_label=QLabel('00:00:00.000');transport.addWidget(self.time_label);transport.addStretch();transport.addWidget(self.filtered)
        marking=QHBoxLayout();content.addLayout(marking)
        button('Mark in (I)',self.set_mark_in,marking);button('Mark out (O)',self.set_mark_out,marking)
        self.mark_button=button('Mark start (M)',self.mark_toggle,marking)
        button('Add selected range',self.commit_range,marking)
        self.space_marks=QCheckBox('Space marks start/end');marking.addWidget(self.space_marks)
        self.mark_label=QLabel('No range selected');marking.addWidget(self.mark_label);marking.addStretch()
        button('−',lambda:self.timeline.zoom(1/1.5),marking);button('+',lambda:self.timeline.zoom(1.5),marking)
        button('Fit',lambda:self.timeline.fit(),marking)
        self.timeline=Timeline()
        wave_row=QHBoxLayout();content.addLayout(wave_row)
        self.waveform=self.timeline;wave_row.addWidget(self.timeline,1)
        self.wave_timer=QTimer(self);self.wave_timer.setInterval(100);self.wave_timer.timeout.connect(self.waveform.update);self.wave_timer.start()
        self.timeline.seekRequested.connect(self.seek_source)
        self.timeline.sceneSelected.connect(self.select_scene)
        self.timeline.boundaryChanged.connect(self.trim_scene)
        self.timeline.rangeSelected.connect(self.select_range)
        self.timeline.gainChanged.connect(self.change_timeline_gain)
        range_panel=QGroupBox('Video detection');content=QVBoxLayout(range_panel);content.setContentsMargins(0,0,0,0)
        self.editor_tabs=QTabWidget();range_scroll=QScrollArea();range_scroll.setWidgetResizable(True);range_scroll.setWidget(range_panel);self.editor_tabs.addTab(range_scroll,self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),"Video")
        self.workspace_splitter.addWidget(self.editor_tabs)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setSizes([480,360])
        self.video_shortcuts=presets.buttons(content,presets.VIDEO,self.video_preset)
        filters=QHBoxLayout(); content.addLayout(filters)
        category_row=filters
        filters.addWidget(QLabel('Filter categories'))
        self.categories=QLineEdit(); self.categories.setPlaceholderText('gore, violence, nudity, mature subject matter');filters.addWidget(self.categories)
        filters=QHBoxLayout();content.addLayout(filters)
        filters.addWidget(QLabel('Padding on each side'))
        self.padding=QDoubleSpinBox(); self.padding.setRange(0,30); self.padding.setSingleStep(.25);self.padding.setValue(.75);self.padding.setSuffix(' s');filters.addWidget(self.padding)
        effects_row=QHBoxLayout();content.addLayout(effects_row)
        effects_row.addWidget(QLabel('When matched'))
        from visual_effects import OPTIONS
        self.video_action=QComboBox()
        for label,value in OPTIONS:self.video_action.addItem(label,value)
        self.video_action.setToolTip('Treatment for the next video scan. Apply changes selected visual findings. Skip is the default.')
        effects_row.addWidget(self.video_action)
        apply_effect=QPushButton('Apply to selected');apply_effect.clicked.connect(self.apply_video_action);effects_row.addWidget(apply_effect)
        self.summary=QLabel('No scenes marked.');content.addWidget(self.summary)
        from detection_balance import DetectionBalance
        self.precision=DetectionBalance();content.addWidget(self.precision)
        self.categories.textChanged.connect(self.update_summary)
        self.padding.valueChanged.connect(self.update_summary)
        splitter=QSplitter();content.addWidget(splitter,1)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(['Enabled','Start','End','Category','Review','Source','Action','Words / replacement'])
        from findings_flash import FindingsFlash
        self.findings_flash=FindingsFlash(self.table);self.table.setItemDelegate(self.findings_flash)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setDragEnabled(False)
        self.table.setToolTip('Shift-click, Ctrl-click, or drag across rows to select multiple ranges.')
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(self.edit_scene)
        self.table.itemChanged.connect(self.toggle_scene)
        self.table.itemSelectionChanged.connect(self.table_selection)
        splitter.addWidget(self.table)
        preview=QWidget(); pl=QVBoxLayout(preview)
        self.preview=QLabel('Scene preview is hidden.\nSelect a scene and choose Reveal frame.');self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setMinimumSize(310,190);self.preview.setWordWrap(True)
        pl.addWidget(self.preview)
        self.preview.hide()
        reveal=QPushButton('Reveal frame at scene start');reveal.clicked.connect(self.reveal);pl.addWidget(reveal)
        reveal.hide()
        self.inspector_host=QWidget();self.inspector_layout=QVBoxLayout(self.inspector_host)
        self.inspector_layout.setContentsMargins(0,0,0,0);pl.addWidget(self.inspector_host)
        self.inline_editor=None;self.inspector_host.hide()
        self.preview_tools=QWidget();pl.addWidget(self.preview_tools);pl=QVBoxLayout(self.preview_tools);pl.setContentsMargins(0,0,0,0)
        self.selection_label=QLabel('No ranges selected');pl.addWidget(self.selection_label)
        context=QFormLayout();pl.addLayout(context)
        self.preview_before=QDoubleSpinBox();self.preview_after=QDoubleSpinBox()
        for spin in (self.preview_before,self.preview_after):
            spin.setRange(0,120);spin.setSingleStep(.5);spin.setValue(3);spin.setSuffix(' s')
        context.addRow('Preview before scene',self.preview_before)
        context.addRow('Preview after scene',self.preview_after)
        self.preview_button=QPushButton('Preview selected scene')
        self.preview_button.clicked.connect(self.preview_scene);pl.addWidget(self.preview_button)
        preview_note=QLabel('Preview uses the selected Original / Filtered mode.');preview_note.setWordWrap(True);pl.addWidget(preview_note)
        self.preview_button.setToolTip('Preview this range with context. Audio filters are applied when enabled below; video cuts are ignored. Click again to pause/resume.')
        note=QLabel('Select a row to inspect its original footage. Double-click to edit times.\n\n←/→: frame • Ctrl+←/→: 5s\nSpace: play/pause • I/O: in/out\nM: mark • [ / ]: previous/next\n+/− or wheel: zoom • Shift-wheel: pan\nDrag timeline: select range • Delete: remove selected');note.setWordWrap(True);note.setObjectName('muted');pl.addWidget(note)
        pl.addStretch();splitter.addWidget(preview);splitter.setSizes([700,330])
        edits=QHBoxLayout();content.addLayout(edits)
        button('Add scene',self.add_scene,edits);button('Edit selected',self.edit_scene,edits);button('Remove selected',self.remove_scene,edits);edits.addStretch()
        button('Enable selected',lambda:self.set_selected_enabled(True),edits)
        button('Disable selected',lambda:self.set_selected_enabled(False),edits)
        scanrow=QHBoxLayout();content.insertLayout(0,scanrow)
        scanrow.addWidget(QLabel('Local vision model'))
        self.models=QComboBox();self.models.setMinimumWidth(150);scanrow.addWidget(self.models)
        self.model_variant=QComboBox();self.model_variant.setMinimumWidth(180);scanrow.addWidget(self.model_variant)
        self.model_description=QLabel();self.model_description.setWordWrap(True);content.insertWidget(1,self.model_description)
        self.models.currentIndexChanged.connect(self.model_family_changed)
        button('Find models',self.find_models,scanrow)
        category_row.addWidget(QLabel('Interval'))
        self.step=QDoubleSpinBox();self.step.setRange(.5,10);self.step.setValue(2);self.step.setSuffix(' s');category_row.addWidget(self.step)
        button('Scan',self.scan_video,category_row)
        self.audio_panel=AudioPanel(self);audio_scroll=QScrollArea();audio_scroll.setWidgetResizable(True);audio_scroll.setWidget(self.audio_panel);self.editor_tabs.addTab(audio_scroll,'Audio / subtitles')
        export_scroll=QScrollArea();export_scroll.setWidgetResizable(True);export_scroll.setWidget(self.audio_panel.export_panel)
        self.editor_tabs.addTab(export_scroll,self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),'Export')
        self.editor_tabs.setCurrentIndex(0)
        self.populate_models((model_catalog.CATALOG,set()))
        helptext=QLabel('Detection is experimental: sampled frames can miss brief scenes. Suggestions are marked for review. Models download on first use; detection runs locally.');helptext.setWordWrap(True);helptext.setObjectName('muted');layout.addWidget(helptext)
        self.status=QLabel('Ready');self.status.setWordWrap(True);layout.addWidget(self.status)
        import workspace
        workspace.install(self,playback_panel,transport,marking,wave_row,content,edits,preview)
        self.content.setEnabled(False)
        # Let file drops reach the window, including over editable fields and the table.
        for child in self.findChildren(QWidget):
            child.setAcceptDrops(False)
        self.setAcceptDrops(True)
        self.shortcuts=[]
        delete=QShortcut(QKeySequence('Delete'),self);delete.setContext(Qt.ShortcutContext.ApplicationShortcut);delete.activated.connect(lambda:self.hotkey(self.remove_scene));self.shortcuts.append(delete)
        for key,step in [('Up',1),('Down',-1),('Shift+Up',.1),('Shift+Down',-.1)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(lambda step=step:self.hotkey(lambda:self.step_timeline_gain(step)));self.shortcuts.append(shortcut)
        for key,action in [('Space',self.space_action),('Left',lambda:self.jog_frame(-1)),('Right',lambda:self.jog_frame(1)),
            (',',lambda:self.jog_frame(-1)),('.',lambda:self.jog_frame(1)),('Ctrl+Left',lambda:self.jog_seconds(-5)),
            ('Ctrl+Right',lambda:self.jog_seconds(5)),('I',self.set_mark_in),('O',self.set_mark_out),('M',self.mark_toggle),
            ('[',lambda:self.jump_mark(-1)),(']',lambda:self.jump_mark(1)),('+',lambda:self.timeline.zoom(1.5)),
            ('=',lambda:self.timeline.zoom(1.5)),('-',lambda:self.timeline.zoom(1/1.5)),('Ctrl+0',lambda:self.timeline.fit())]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(lambda fn=action:self.hotkey(fn));self.shortcuts.append(shortcut)
    def save_layout(self):
        self.settings['dock_layout_v35']=bytes(self.dock_host.saveState().toBase64()).decode()
        DATA.mkdir(parents=True,exist_ok=True);core.atomic_text(SETTINGS,json.dumps(self.settings))
        self.status.setText('Workspace layout saved.')
    def hotkey(self,action):
        if not self.doc or not self.content.isEnabled() or QApplication.activeModalWidget():return
        focus=QApplication.focusWidget()
        if isinstance(focus,(QLineEdit,QDoubleSpinBox,QComboBox)):return
        action()
    def player_key(self,key):
        if not self.content.isEnabled():return
        if key=='focus':self.play();self.video_overlay.reveal();return
        self.timeline.setFocus()
        actions={'delete':self.remove_scene,'gain-up':lambda:self.step_timeline_gain(1),'gain-down':lambda:self.step_timeline_gain(-1),'gain-fine-up':lambda:self.step_timeline_gain(.1),'gain-fine-down':lambda:self.step_timeline_gain(-.1),'space':self.space_action,'left':lambda:self.jog_frame(-1),'right':lambda:self.jog_frame(1),
                 'back':lambda:self.jog_seconds(-5),'forward':lambda:self.jog_seconds(5),
                 'in':self.set_mark_in,'out':self.set_mark_out,'mark':self.mark_toggle,
                 'previous':lambda:self.jump_mark(-1),'next':lambda:self.jump_mark(1),
                 'zoom-in':lambda:self.timeline.zoom(1.5),'zoom-out':lambda:self.timeline.zoom(1/1.5)}
        if key in actions:self.hotkey(actions[key])
    def update_play_glyphs(self,paused):
        if hasattr(self,'preview_button'):
            self.preview_button.setText(('Resume preview' if paused else 'Pause preview') if self.playback_mode=='preview' else 'Preview selected scene')
        for button in (self.play_button,):set_glyph(button,'play' if paused else 'pause',('Play' if paused else 'Pause')+' (Space)')
    def space_action(self):
        self.mark_toggle() if self.space_marks.isChecked() else self.play()
    def position_changed(self,t):
        self.source_position=t;self.timeline.set_position(t);self.timeline.ensure_visible(t)
        if self.embedded.paused and self.mark_start is not None and self.mark_end is not None:
            self.subtitle_sidebar.follow(self.mark_start,self.mark_end)
        elif self.embedded.paused and len(self.selected_rows())==1:
            scene=self.doc['scenes'][self.selected_rows()[0]];self.subtitle_sidebar.follow(scene['start'],scene['end'])
        else:self.subtitle_sidebar.follow(t)
        self.waveform.update()
        mode='Original' if self.playback_mode=='original' else 'Filtered' if self.playback_mode=='filtered' else 'Preview'
        self.time_label.setText(f'{core.clock(t)} / {core.clock(self.doc["duration"])}{" • Preview" if mode=="Preview" else ""}' if self.doc else core.clock(t))
    def load_embedded(self,paused=True,position=None,preview=None):
        if not self.doc:return
        self.reload_timer.stop()
        position=self.source_position if position is None else position
        playback_doc=copy.deepcopy(self.doc) if preview else self.doc
        if preview:playback_doc["_preview_range"]=list(preview)
        import visual_effects
        rendered=self.filtered.isChecked() and bool(visual_effects.scenes(self.doc,self.labels(),self.padding.value()) or media.audio_scenes(self.doc) or self.doc.get('normalize_audio'))
        if preview and self.filtered.isChecked():
            kept=core.kept_ranges(self.doc['duration'],core.cuts(self.doc,self.labels(),self.padding.value()))
            if not any(max(a,preview[0])<min(b,preview[1]) for a,b in kept):
                self.empty_preview=True;self.preview_bounds=preview;self.playback_mode='preview'
                self.embedded.pause();self.status.setText('This segment is entirely skipped in Filtered mode. Select Original to review it.');return
        audio_path=None
        if self.filtered.isChecked() and (rendered or media.audio_scenes(self.doc) or self.doc.get('normalize_audio')):
            import playback_audio
            audio_path=playback_audio.cache_path(self.temp.name,self.video,playback_doc,self.labels(),self.padding.value(),rendered)
            if not audio_path.exists() and str(audio_path)!=getattr(self,'silent_audio_key',None):
                if self.job_active:
                    QTimer.singleShot(100,lambda:self.load_embedded(paused,position,preview));return
                video=self.video;doc=copy.deepcopy(playback_doc);labels=set(self.labels());padding=self.padding.value()
                self.cancel.clear()
                def ready(result):
                    if result is None:self.silent_audio_key=str(audio_path)
                    QTimer.singleShot(0,lambda:self.load_embedded(paused,position,preview))
                self.run_job(lambda progress:playback_audio.prepare(audio_path,video,doc,labels,padding,progress,self.cancel,rendered),ready,True)
                def failed(_):
                    self.filtered.blockSignals(True);self.filtered.setChecked(getattr(self,'loaded_filtered',False));self.filtered.blockSignals(False)
                self.worker.failure.connect(failed)
                return
            if not audio_path.exists():audio_path=None
        try:
            ranges=core.kept_ranges(self.doc['duration'],core.cuts(self.doc,self.labels(),self.padding.value())) if self.filtered.isChecked() else [(0,self.doc['duration'])]
            if preview:ranges=[(max(a,preview[0]),min(b,preview[1])) for a,b in ranges if max(a,preview[0])<min(b,preview[1])]
            if not ranges:
                self.embedded.pause();self.status.setText('This segment is entirely skipped in Filtered mode. Select Original to review it.');return
            self.embedded.start(self.mpv())
            if self.filtered.isChecked():
                if rendered:path=audio_path
                else:
                    self.jobs+=1;path=Path(self.temp.name)/f'embedded-{self.jobs}.edl'
                    core.atomic_text(path,core._mpv_ranges(self.video,ranges))
                self.playback_mode='filtered'
            else:
                path=self.video;self.playback_mode='original'
                if preview:
                    self.jobs+=1;path=Path(self.temp.name)/f'preview-{self.jobs}.edl';core.atomic_text(path,core._mpv_ranges(self.video,ranges))
            self.empty_preview=False;self.loaded_filtered=self.filtered.isChecked();self.preview_bounds=preview
            if preview:self.playback_mode='preview'
            self.embedded.load(path,ranges,position,paused,audio_path=None if rendered else audio_path,rendered=rendered)
        except Exception as e:self.error(str(e))
    def original_for_edit(self):
        if not self.doc:return
        if self.playback_mode=='preview':self.load_embedded(paused=True)
        else:self.embedded.pause()
    def seek_source(self,t):
        if self.doc:self.load_embedded(paused=True,position=t)
    def seek_subtitle(self,t):
        self.table.clearSelection();self.mark_start=self.mark_end=None;self.update_marks()
        self.seek_source(t);self.subtitle_sidebar.follow(t)
    def jog_frame(self,direction):
        if not self.doc:return
        self.original_for_edit();self.embedded.step(direction)
    def jog_seconds(self,seconds):
        if self.doc:self.seek_source(max(0,min(self.doc['duration'],self.source_position+seconds)))
    def select_scene(self,row):
        if 0<=row<self.table.rowCount():self.table.selectRow(row)
    def table_selection(self):
        rows=self.selected_rows();row=self.table.currentRow()
        self.timeline.selected=row if row in rows else -1;self.timeline.selected_rows=set(rows);self.timeline.update()
        self.selection_label.setText(f'{len(rows)} ranges selected')
        if hasattr(self,'audio_panel'):self.audio_panel.update_apply_state()
        self.hide_inspector()
        if self.doc and len(rows)==1:
            scene=self.doc['scenes'][rows[0]];self.seek_source(scene['start']);self.subtitle_sidebar.follow(scene['start'],scene['end'])
    def change_timeline_gain(self,row,db):
        if not self.doc or not self.selected_rows():return
        rows=self.selected_rows()
        if row<0:
            for start,end in list(dict.fromkeys((self.doc['scenes'][r]['start'],self.doc['scenes'][r]['end']) for r in rows)):
                self.set_gain_interval(start,end,db)
        elif row in rows and self.doc['scenes'][row].get('action')=='gain':
            scene=self.doc['scenes'][row];scene['gain_db']=db;scene['reviewed']=True;self.dirty=True;self.update_summary()
    def set_gain_interval(self,start,end,db):
        for i,scene in enumerate(self.doc['scenes']):
            if scene.get('action')=='gain' and abs(scene['start']-start)<.001 and abs(scene['end']-end)<.001:
                scene['gain_db']=db;scene['reviewed']=True;self.dirty=True;self.update_summary();return i
        self.doc['scenes'].append(dict(start=start,end=end,category='audio volume',action='gain',gain_db=db,enabled=True,reviewed=True,source='manual'))
        rows=self.selected_rows();self.dirty=True;self.refresh()
        for row in rows:self.table.selectionModel().select(self.table.model().index(row,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        return len(self.doc['scenes'])-1
    def step_timeline_gain(self,step):
        if not self.doc:return
        rows=self.selected_rows()
        if not rows:return
        intervals=list(dict.fromkeys((self.doc['scenes'][r]['start'],self.doc['scenes'][r]['end']) for r in rows))
        for start,end in intervals:
            current=next((s.get('gain_db',0) for s in self.doc['scenes'] if s.get('action')=='gain' and abs(s['start']-start)<.001 and abs(s['end']-end)<.001),0)
            self.set_gain_interval(start,end,max(-60,min(12,current+step)))
        self.status.setText('Gain adjusted. Up/Down: 1 dB; Shift+Up/Down: 0.1 dB. Use Filtered playback to audition.')
    def jump_mark(self,direction):
        if not self.doc:return
        points=sorted((s['start'],i) for i,s in enumerate(self.doc['scenes']))
        choices=[p for p in points if p[0]>self.source_position+.01] if direction>0 else [p for p in points if p[0]<self.source_position-.01]
        if choices:self.select_scene((choices[0] if direction>0 else choices[-1])[1]);self.seek_source((choices[0] if direction>0 else choices[-1])[0])
    def update_marks(self):
        self.timeline.pending=self.mark_start;self.timeline.selection=(self.mark_start,self.mark_end) if self.mark_start is not None and self.mark_end is not None else None;self.timeline.update()
        self.mark_button.setText('Mark end (M)' if self.mark_start is not None else 'Mark start (M)')
        self.mark_label.setText(('In '+core.clock(self.mark_start) if self.mark_start is not None else 'No range selected')+(' • Out '+core.clock(self.mark_end) if self.mark_end is not None else ''))
    def set_mark_in(self):
        if not self.doc:return
        self.original_for_edit();self.mark_start=self.source_position;self.mark_end=None;self.update_marks()
    def set_mark_out(self):
        if not self.doc:return
        self.original_for_edit();self.mark_end=self.source_position;self.update_marks()
    def mark_toggle(self):
        if self.mark_start is None:self.set_mark_in()
        else:self.set_mark_out();self.commit_range()
    def select_range(self,start,end):
        self.subtitle_sidebar.follow(start,end)
        self.original_for_edit();self.table.clearSelection();self.mark_start=start;self.mark_end=end;self.update_marks()
    def commit_range(self):
        if not self.doc:return
        if self.mark_start is None or self.mark_end is None or not self.mark_start<self.mark_end:
            self.status.setText('Set an in point and a later out point first (I/O, M twice, or drag along the timeline).');return
        category=next(iter(sorted(self.labels())),'gore')
        self.doc['scenes'].append({'start':self.mark_start,'end':self.mark_end,'category':category,
            'action':'skip','enabled':True,'reviewed':True,'source':'manual'})
        self.dirty=True;self.mark_start=self.mark_end=None;self.refresh();self.update_marks()
        self.table.selectRow(len(self.doc['scenes'])-1);self.status.setText('Skip range added. Save scenes to keep it.')
    def trim_scene(self,row,start,end):
        if not self.doc or not 0<=row<len(self.doc['scenes']):return
        if not 0<=start<end<=self.doc['duration']:return
        self.original_for_edit();self.doc['scenes'][row].update(start=start,end=end,reviewed=True,source='manual')
        self.dirty=True;self.refresh();self.table.selectRow(row)
    def dropped_video(self, mime):
        if self.job_active:return None
        if not mime.hasUrls():return None
        urls=mime.urls()
        if len(urls)!=1 or not urls[0].isLocalFile():return None
        path=Path(urls[0].toLocalFile())
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:return None
        return str(path)
    def dragEnterEvent(self,event):
        if self.dropped_video(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:event.ignore()
    def dragMoveEvent(self,event):
        self.dragEnterEvent(event)
    def dropEvent(self,event):
        path=self.dropped_video(event.mimeData())
        if not path:
            event.ignore();return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.open_video_path(path)
    def error(self,text):
        self.status.setText(text)
        QMessageBox.warning(self,'SceneSieve',text)
    def run_job(self,fn,done,cancellable=False):
        if self.job_active: return
        self.job_active=True
        if self.doc:self.embedded.pause()
        self.content.setEnabled(False)
        for b in self.buttons:b.setEnabled(False)
        self.progress_dialog=None
        if cancellable:
            from scan_progress import ScanProgress
            self.progress_dialog=ScanProgress(self,self.cancel_scan,self.doc['duration'] if self.doc else 0)
            self.progress_dialog.show()
        self.worker=Worker(fn)
        self.worker.progress.connect(self.status.setText)
        if self.progress_dialog:self.worker.progress.connect(self.progress_dialog.update_progress)
        self.worker.result.connect(done)
        self.worker.failure.connect(self.job_failed)
        self.worker.finished.connect(self.job_done)
        self.worker.start()
    def close_progress(self):
        dialog=getattr(self,'progress_dialog',None)
        if dialog:dialog.done(0);dialog.deleteLater();self.progress_dialog=None
    def job_failed(self,text):
        self.close_progress();self.error(text)
    def job_done(self):
        self.close_progress()
        self.job_active=False
        for b in self.buttons:b.setEnabled(True)
        self.content.setEnabled(self.doc is not None)
        self.audio_panel.update_apply_state()
    def discard(self):
        if not self.dirty:return True
        choice=QMessageBox.question(self,'Unsaved scenes','Save your scene changes before continuing?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if choice==QMessageBox.StandardButton.Cancel:return False
        if choice==QMessageBox.StandardButton.Save:return self.save_scenes()
        return True
    def open_video(self):
        path,_=QFileDialog.getOpenFileName(self,'Open video','','Videos (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;All files (*)')
        if not path:return
        self.open_video_path(path)
    def open_video_path(self,path):
        if self.job_active:return
        if not self.discard():return
        self.status.setText('Reading video and computing its fingerprint…');self.cancel.clear()
        def load(progress):
            progress('Loading media 0/4 — reading video information')
            duration=scanner.probe(path)
            if self.cancel.is_set():raise InterruptedError('Media loading cancelled.')
            progress('Loading media 1/4 — identifying the file')
            identity=core.fingerprint(path)
            if self.cancel.is_set():raise InterruptedError('Media loading cancelled.')
            progress('Loading media 2/4 — checking saved scenes')
            doc={'version':1,'video':Path(path).name,'fingerprint':identity,'duration':duration,'scenes':[]}
            sidecar=Path(self.settings.get('output_dir',str(Path(path).parent)))/(Path(path).stem+'.scenes.json')
            if not sidecar.exists():sidecar=Path(path).with_suffix('.scenes.json')
            warning=''
            if sidecar.exists():
                try:
                    loaded=core.validate(json.loads(sidecar.read_text(encoding='utf-8')),identity)
                    if abs(loaded['duration']-duration)>.1:raise ValueError('Duration mismatch.')
                    doc=loaded
                except Exception as e: warning='Scene file was not loaded: '+str(e)
            progress('Loading media 3/4 — preparing saved audio treatments')
            replacements.prepare_all(doc['scenes'],progress,self.cancel)
            if self.cancel.is_set():raise InterruptedError('Media loading cancelled.')
            progress('Loading media 4/4 — opening the player')
            return path,doc,warning
        def done(result):
            self.video,self.doc,warning=result;self.dirty=False
            self.source_position=0.;self.mark_start=self.mark_end=None;self.update_marks()
            self.file_label.setText(f'{Path(self.video).name}  •  {core.clock(self.doc["duration"])}')
            self.refresh();self.status.setText(warning or 'Video ready. Add scenes or scan with a local vision model.')
            self.audio_panel.normalize.blockSignals(True);self.audio_panel.normalize.setChecked(bool(self.doc.get('normalize_audio')));self.audio_panel.normalize.blockSignals(False)
            self.waveform.data={'step':.05,'peak':[],'rms':[]}
            self.load_embedded(paused=True,position=0.)
            QTimer.singleShot(100,self.analyse_waveform)
        self.run_job(load,done,True)
    def refresh(self):
        self.table.blockSignals(True);self.table.setRowCount(len(self.doc['scenes']))
        for row,s in enumerate(self.doc['scenes']):
            check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsUserCheckable);check.setCheckState(Qt.CheckState.Checked if s['enabled'] else Qt.CheckState.Unchecked);self.table.setItem(row,0,check)
            for col,value in enumerate([core.clock(s['start']),core.clock(s['end']),s['category'],'Checked' if s['reviewed'] else 'Needs review',s.get('source','imported'),visual_effects.LABELS.get(s.get('action'),s.get('action','skip')),(s.get('text','')+' → '+s.get('replacement','') if s.get('action')=='replace' else s.get('text',''))],1):self.table.setItem(row,col,QTableWidgetItem(value))
        self.table.blockSignals(False)
        self.update_summary()
        self.preview.setPixmap(QPixmap());self.preview.setText('Scene preview is hidden.\nSelect a scene and choose Reveal frame.')
    def toggle_scene(self,item):
        if item.column()==0:self.doc['scenes'][item.row()]['enabled']=item.checkState()==Qt.CheckState.Checked;self.dirty=True;self.update_summary()
    def update_summary(self,*_):
        if not self.doc:return
        self.findings_flash.update_scenes(self.doc['scenes'])
        if hasattr(self,'audio_panel'):
            self.audio_panel.update_apply_state();self.audio_panel.export_panel.sync_source()
        self.subtitle_sidebar.set_cues(media.display_subtitles(self.doc));self.subtitle_sidebar.follow(self.source_position)
        if hasattr(self,'docks'):
            available=bool(self.subtitle_sidebar.cues)
            if available!=getattr(self,'subtitle_available',False):self.docks['Subtitles'].setVisible(available)
            self.subtitle_available=available
        ranges=core.cuts(self.doc,self.labels(),self.padding.value())
        excluded=sum(b-a for a,b in ranges)
        pending=sum(not s['reviewed'] for s in self.doc['scenes'])
        self.summary.setText(f'{len(ranges)} skip ranges • {excluded:.2f}s excluded • {pending} scenes need review' if ranges else 'No matching skip ranges — playback will include the entire video.')
        audio_count=len(media.audio_scenes(self.doc))
        import visual_effects
        visual_count=len(visual_effects.scenes(self.doc,self.labels(),self.padding.value()))
        if visual_count:self.summary.setText(self.summary.text()+f' • {visual_count} visual effects')
        if audio_count:self.summary.setText(self.summary.text()+f' • {audio_count} audio filters')
        self.timeline.set_data(self.doc['duration'],self.doc['scenes'],self.labels())
        if self.filtered.isChecked() and self.embedded.ready:self.embedded.pause();self.reload_timer.start()
    def selected(self):
        rows=self.selected_rows()
        if len(rows)!=1:raise ValueError('Select one range to edit or preview. Bulk actions apply to all selected ranges.')
        return rows[0]
    def selected_rows(self):
        return sorted(index.row() for index in self.table.selectionModel().selectedRows())
    def show_inline_editor(self,row=None):
        if self.inline_editor:
            self.inspector_layout.removeWidget(self.inline_editor);self.inline_editor.deleteLater()
        editor=SceneDialog(self,self.doc['duration'],self.doc['scenes'][row] if row is not None else None)
        editor.setWindowFlags(Qt.WindowType.Widget)
        self.inline_editor=editor;self.inspector_layout.addWidget(editor)
        def save():
            value=dict(editor.value)
            def done(_):
                if row is None:self.doc['scenes'].append(value)
                else:self.doc['scenes'][row]=value
                self.dirty=True;self.hide_inspector();self.refresh()
            if value['action'] in ('bleep','replace'):self.run_job(lambda p:replacements.prepare_all([value],p),done)
            else:done(None)
        editor.accepted.connect(save);editor.rejected.connect(self.hide_inspector)
        self.preview_tools.hide();self.inspector_host.show();editor.show();editor.start.setFocus()
    def hide_inspector(self):
        self.inspector_host.hide();self.preview_tools.show()
    def add_scene(self):
        if self.doc:self.show_inline_editor()
    def edit_scene(self,*_):
        try:self.show_inline_editor(self.selected())
        except Exception as e:self.error(str(e))
    def set_selected_enabled(self,enabled):
        if not self.doc:return
        rows=self.selected_rows()
        for row in rows:self.doc['scenes'][row]['enabled']=enabled
        if rows:self.dirty=True;self.refresh()
    def remove_scene(self):
        if not self.doc:return
        rows=self.selected_rows()
        if not rows:
            self.mark_start=self.mark_end=None;self.update_marks();return
        self.table.clearSelection();self.hide_inspector()
        for row in reversed(rows):del self.doc['scenes'][row]
        self.dirty=True;self.refresh()
    def save_scenes(self):
        if not self.doc:return False
        path,_=QFileDialog.getSaveFileName(self,'Save scene file',str(self.output_dir()/(Path(self.video).stem+'.scenes.json')),'Scene files (*.json)')
        if not path:return False
        try:core.save(path,self.doc);self.dirty=False;self.status.setText('Saved '+path);return True
        except Exception as e:self.error(str(e));return False
    def load_scenes(self):
        if not self.doc or not self.discard():return
        path,_=QFileDialog.getOpenFileName(self,'Load scene file','','Scene files (*.json)')
        if not path:return
        try:
            doc=core.validate(json.loads(Path(path).read_text(encoding='utf-8')),self.doc['fingerprint'])
            if abs(doc['duration']-self.doc['duration'])>.1:raise ValueError('Duration mismatch.')
            def done(_):self.doc=doc;self.dirty=False;self.refresh();self.status.setText('Loaded '+path)
            self.run_job(lambda p:replacements.prepare_all(doc['scenes'],p),done)
        except Exception as e:self.error(str(e))
    def labels(self):return {s.strip() for s in self.categories.text().split(',') if s.strip()}
    def export(self,kind=None,path=None):
        if not self.doc:return
        ok=True
        if not kind:kind,ok=QInputDialog.getItem(self,'Export player file','Player / format',list(player_exports.FORMATS),0,False)
        if not ok:return
        warning=player_exports.limitation(kind,self.doc)
        choice=QMessageBox.warning(self,'Export compatibility — '+kind,warning+'\n\nContinue with this limited export?',QMessageBox.StandardButton.Ok|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
        if choice!=QMessageBox.StandardButton.Ok:return
        extension=player_exports.FORMATS[kind]
        if not path:path,_=QFileDialog.getSaveFileName(self,'Export '+kind,str(self.output_dir()/(Path(self.video).stem+extension)),f'{kind} (*{extension})')
        if not path:return
        try:
            if Path(path).resolve()==Path(self.video).resolve():raise ValueError('Choose a sidecar filename; the source video cannot be overwritten.')
            core.atomic_text(path,player_exports.export_text(kind,self.video,self.doc,self.labels(),self.padding.value()))
            self.status.setText('Exported '+path)
            QMessageBox.information(self,'Export completed — compatibility reminder',path+'\n\n'+warning)
        except Exception as e:self.error(str(e))
    def mpv(self):
        for path in [os.environ.get('SCENESIEVE_MPV'),str(BIN/'mpv.exe'),str(ROOT/'bin'/'mpv.exe'),str(ROOT/'bin'/'mpv'),shutil.which('mpv')]:
            if path and Path(path).is_file():return path
        path,_=QFileDialog.getOpenFileName(self,'Locate mpv executable (install from mpv.io)')
        if not path:raise ValueError('mpv was not found. Install mpv or put its executable in the bin folder.')
        os.environ['SCENESIEVE_MPV']=path
        return path
    def play(self):
        if not self.doc:return
        if self.playback_mode=='preview':
            position=self.source_position if self.source_position<self.doc['duration']-.1 else 0.
            self.load_embedded(paused=False,position=position);self.update_play_glyphs(False);return
        if self.embedded.paused and self.source_position>=self.doc['duration']-.1:
            self.load_embedded(paused=False,position=0.);return
        if self.filtered.isChecked() and not core.kept_ranges(self.doc['duration'],core.cuts(self.doc,self.labels(),self.padding.value())):
            self.embedded.pause();self.status.setText('Nothing to play: the selected filters exclude the entire video.');return
        if self.reload_timer.isActive():self.load_embedded(paused=False)
        elif not self.embedded.ready:self.load_embedded(paused=False)
        else:self.embedded.pause(not self.embedded.paused)
    def reveal(self):
        try:
            s=self.doc['scenes'][self.selected()];cap=cv2.VideoCapture(self.video)
            try:cap.set(cv2.CAP_PROP_POS_MSEC,s['start']*1000);ok,frame=cap.read()
            finally:cap.release()
            if not ok:raise ValueError('Cannot read this frame.')
            rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB);h,w=rgb.shape[:2]
            image=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy()
            self.preview.setPixmap(QPixmap.fromImage(image).scaled(360,240,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        except Exception as e:self.error(str(e))
    def preview_scene(self):
        if not self.doc:return
        if self.playback_mode=='preview' and getattr(self,'preview_row',None)==self.table.currentRow() and self.embedded.ready and not getattr(self,'empty_preview',False):
            if self.embedded.paused and self.embedded.ranges and self.source_position>=self.embedded.ranges[-1][1]-.1:self.embedded.seek(self.embedded.ranges[0][0])
            self.embedded.pause(not self.embedded.paused);self.update_play_glyphs(self.embedded.paused);return
        try:
            scene=self.doc['scenes'][self.selected()]
            start=max(0,scene['start']-self.preview_before.value())
            end=min(self.doc['duration'],scene['end']+self.preview_after.value())
            self.preview_row=self.table.currentRow()
            self.status.setText(f'Previewing scene in {"Filtered" if self.filtered.isChecked() else "Original"} mode: {core.clock(start)}–{core.clock(end)}.')
            self.load_embedded(paused=False,position=start,preview=(start,end))
        except Exception as e:self.error(str(e))
    def selected_model(self):
        return self.model_variant.currentData() or ''
    def populate_models(self,result):
        names,self.installed_models=result;current=self.selected_model() or 'gemma3:4b'
        self.model_groups=model_catalog.group_variants(names)
        self.models.blockSignals(True);self.models.clear();self.models.addItems(sorted(self.model_groups))
        family=current.partition(':')[0];index=self.models.findText(family);self.models.setCurrentIndex(max(0,index));self.models.blockSignals(False)
        self.model_family_changed()
        index=self.model_variant.findData(current)
        if index>=0:self.model_variant.setCurrentIndex(index)
    def model_family_changed(self,*_):
        family=self.models.currentText();self.model_variant.clear()
        variants=getattr(self,'model_groups',{}).get(family,[])
        for name in variants:self.model_variant.addItem(name.partition(':')[2]+(' [installed]' if name in self.installed_models else ' [download on scan]'),name)
        self.model_variant.setVisible(len(variants)>1)
        self.model_description.setText(model_catalog.family_description(family))
        preferred=next((n for n in variants if n.endswith(':4b')),next((n for n in variants if n.endswith(':latest')),variants[0] if variants else ''))
        self.model_variant.setCurrentIndex(self.model_variant.findData(preferred))
    def find_models(self):
        self.run_job(lambda _:model_catalog.catalog(True),self.populate_models)
    def choose_output(self):
        folder=QFileDialog.getExistingDirectory(self,'Scene and media output folder',str(self.output_dir()))
        if folder:
            self.settings['output_dir']=folder;DATA.mkdir(parents=True,exist_ok=True);core.atomic_text(SETTINGS,json.dumps(self.settings));self.output_label.setText(folder)
    def output_dir(self):
        return Path(self.settings.get('output_dir',str(Path(self.video).parent if self.video else Path.home()/'Videos')))
    def analyse_waveform(self):
        if not self.doc:return
        if self.job_active:QTimer.singleShot(150,self.analyse_waveform);return
        video=self.video;self.cancel.clear()
        def done(data):self.waveform.data=data;self.waveform.update();self.status.setText('Audio waveform ready.')
        self.run_job(lambda p:media.waveform(video,p,self.cancel),done,True)
    def audio_seek_settled(self,position):
        if getattr(self.embedded,'audio_path',None) or getattr(self.embedded,'rendered',False):return
        if self.doc and any(s.get('action') in ('bleep','replace') for s in media.audio_scenes(self.doc)):
            self.embedded.position=position;self.apply_audio()
    def apply_audio(self):
        try:self.apply_audio_filters()
        except Exception as e:self.embedded.pause();self.error(str(e))
    def apply_audio_filters(self):
        self.set_playback_volume();self.embedded.command('set_property','speed',self.speed.currentData())
        if self.filtered.isChecked():
            # Map source audio ranges onto the gapless filtered playback clock.
            mapped=[];offset=0.
            for a,b in self.embedded.ranges:
                for scene in media.audio_scenes(self.doc):
                    finish=max(scene['end'],scene['start']+replacements.duration(scene)) if scene['action']=='replace' else scene['end']
                    x,y=max(a,scene['start']),min(b,finish)
                    if y>x:mapped.append({**scene,'start':offset+x-a,'end':offset+y-a,'_mute_end':offset+min(b,scene['end'])-a,'_replacement_end':offset+y-a,'_replacement_source':scene,'_replacement_offset':x-scene['start']})
                offset+=b-a
            if getattr(self.embedded,'audio_path',None) or getattr(self.embedded,'rendered',False):self.embedded.command('set_property','af','')
            else:
                filt=media.audio_filter({'scenes':mapped},normalize=bool(self.doc.get('normalize_audio')),replacement_start=playback_time(self.embedded.position,self.embedded.ranges))
                self.embedded.command('set_property','af','lavfi=['+filt+']')
            self.embedded.command('set_property','sid','no')
            text=media.subtitle_text(self.doc,self.embedded.ranges)
            if text:
                self.jobs+=1;path=Path(self.temp.name)/f'filtered-{self.jobs}.srt';core.atomic_text(path,text)
                self.embedded.command('sub-add',str(path),'select')
        else:self.embedded.command('set_property','af','')
    def set_playback_volume(self):
        self.embedded.command('set_property','volume',100)
        self.embedded.command('set_property','mute',False)

    def video_preset(self,name):
        if not self.doc or (self.job_active):return
        self.categories.setText(presets.value(presets.VIDEO,name));self.scan_video()
    def apply_video_action(self):
        if not self.doc:return
        from visual_effects import ACTIONS
        rows=[r for r in self.selected_rows() if self.doc['scenes'][r]['action'] in ('skip',*ACTIONS)]
        if not rows:self.status.setText('Select visual findings to apply this treatment.');return
        for row in rows:self.doc['scenes'][row]['action']=self.video_action.currentData()
        self.dirty=True;self.refresh()
        self.status.setText(f'Applied {self.video_action.currentText()} to {len(rows)} visual findings. Select Filtered to preview.')
    def scan_video(self):
        if not self.doc:return
        model=self.selected_model();labels=sorted(self.labels())
        if not model or not labels:self.error('Find a local vision model and enter at least one category.');return
        self.cancel.clear();self.status.setText('Starting scan. Video frames are sent only to local Ollama.')
        path,duration,step=self.video,self.doc['duration'],self.step.value()
        precision=self.precision.value();action=self.video_action.currentData()
        def done(scenes):
            scenes=[{**s,'action':action} for s in scenes]
            self.doc['scenes'] = [s for s in self.doc['scenes']
                                  if not (s.get('source') == 'ollama:'+model and s['category'] in labels)]
            self.doc['scenes'].extend(scenes);self.dirty=True;self.refresh()
            self.load_embedded(paused=True,position=0.)
            self.status.setText(f'Scan finished: {len(scenes)} suggested scenes added. Review boundaries and save. A scan with no detections does not guarantee no gore.')
        identity=dict(self.doc['fingerprint'])
        def scan(progress):
            model_catalog.ensure_model(model,progress,self.cancel)
            return scanner.scan(path,duration,model,labels,step,self.cancel,progress,cache_dir=DATA/'scan-cache',identity=identity,precision=precision)
        self.run_job(scan,done,True)
    def cancel_scan(self):
        self.cancel.set();self.status.setText('Cancelling the current operation…')
    def closeEvent(self,event):
        if self.job_active:
            self.cancel_scan();self.status.setText('Please wait for the current operation to finish before closing.');event.ignore();return
        if not self.discard():event.ignore();return
        self.video_overlay.close();self.reload_timer.stop();self.embedded.close()
        for player in self.players:
            if player.state()!=QProcess.ProcessState.NotRunning:player.terminate();player.waitForFinished(1500)
            if player.state()!=QProcess.ProcessState.NotRunning:player.kill();player.waitForFinished(1000)
        self.temp.cleanup();event.accept()

if __name__=='__main__':
    app=QApplication(sys.argv);app.setStyle('Fusion');window=Window();window.show();sys.exit(app.exec())
