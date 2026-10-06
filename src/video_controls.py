"""Transient native-video controls and a synchronized dialogue sidebar."""
import time
from PySide6.QtCore import Qt, QTimer, QPoint,QObject,QEvent,Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QAbstractItemView,QHBoxLayout,QButtonGroup
import core
from dialogue import excerpts
from glyphs import set_glyph

class PlaybackToggle(QWidget):
    toggled=Signal(bool)
    def __init__(self,parent=None):
        super().__init__(parent);self._filtered=False
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(0)
        self.group=QButtonGroup(self);self.group.setExclusive(True)
        self.original=QPushButton('Original');self.filtered=QPushButton('Filtered')
        for button,value in ((self.original,False),(self.filtered,True)):
            button.setCheckable(True);self.group.addButton(button);row.addWidget(button)
            button.clicked.connect(lambda checked=False,value=value:self.setChecked(value))
        self.original.setChecked(True)
        self.original.setToolTip('Play the original video and audio')
        self.filtered.setToolTip('Play with enabled scene cuts and audio treatments')
        self.setStyleSheet('QPushButton{border-radius:0} QPushButton:checked{background:#345b70;border-color:#73bcd9;color:#ffffff;font-weight:600}')
        self.original.setStyleSheet('border-top-left-radius:5px;border-bottom-left-radius:5px')
        self.filtered.setStyleSheet('border-top-right-radius:5px;border-bottom-right-radius:5px')
    def isChecked(self):return self._filtered
    def setChecked(self,value):
        value=bool(value);changed=value!=self._filtered;self._filtered=value
        self.filtered.setChecked(value);self.original.setChecked(not value)
        if changed:self.toggled.emit(value)

class VideoClickFilter(QObject):
    def __init__(self,window):super().__init__(window);self.window=window
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton:
            if self.window.content.isEnabled():self.window.play();self.window.video_overlay.reveal()
            return True
        return False

class VideoOverlay:
    def __init__(self, window):
        self.window=window;self.last_cursor=None;self.inside=False;self.until=0
        self.click_filter=VideoClickFilter(window);window.surface.installEventFilter(self.click_filter)
        # mpv owns a native child window: use an owned, non-activating tool window
        # so the control remains visible above its video surface on Windows.
        self.button=QPushButton(window)
        self.button.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        self.button.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.button.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.setFixedSize(64,64)
        self.button.setStyleSheet('QPushButton,QPushButton:hover,QPushButton:pressed,QPushButton:focus{background:transparent;border:none;padding:0}')
        self.paused(True)
        self.button.clicked.connect(self.toggle)
        self.timer=QTimer(window);self.timer.setInterval(80);self.timer.timeout.connect(self.tick);self.timer.start()
    def reveal(self):
        self.until=time.monotonic()+1.8;self.tick()
    def toggle(self):
        self.window.play();self.reveal()
    def paused(self,value):
        set_glyph(self.button,'play' if value else 'pause','Play' if value else 'Pause',size=34)
    def tick(self):
        w=self.window;cursor=QCursor.pos();surface=w.surface
        inside=surface.rect().contains(surface.mapFromGlobal(cursor))
        if inside and (not self.inside or cursor!=self.last_cursor):self.until=time.monotonic()+1.8
        self.inside=inside;self.last_cursor=cursor
        visible=(w.isVisible() and not w.isMinimized() and (w.isActiveWindow() or any(d.isActiveWindow() for d in getattr(w,'docks',{}).values())) and
                 w.doc is not None and w.content.isEnabled() and time.monotonic()<self.until)
        if visible:
            self.button.move(surface.mapToGlobal(QPoint((surface.width()-self.button.width())//2,(surface.height()-self.button.height())//2)))
            self.button.show();self.button.raise_()
        else:self.button.hide()
    def close(self):
        self.timer.stop();self.button.hide()

class SubtitleSidebar(QWidget):
    def __init__(self,seek,parent=None):
        super().__init__(parent);self.cues=[];self.signature=None
        self.setMinimumWidth(230);self.setMaximumWidth(460)
        layout=QVBoxLayout(self);layout.setContentsMargins(8,0,0,0)
        layout.addWidget(QLabel('Subtitle dialogue'))
        self.caption=QLabel('Closest cue to playhead');layout.addWidget(self.caption)
        self.list=QListWidget();self.list.setWordWrap(True)
        self.list.setStyleSheet('QListWidget{background:#182630;} QListWidget::item{padding:7px;} QListWidget::item:selected{background:#34596b;color:white;}')
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setToolTip('Click a subtitle to seek to its original-video timestamp.')
        self.list.itemClicked.connect(lambda item:seek(self.cues[self.list.row(item)]['start']))
        layout.addWidget(self.list);self.hide()
    def set_cues(self,cues):
        signature=tuple((c['start'],c['end'],c.get('text','')) for c in cues)
        if signature!=self.signature:
            self.signature=signature;self.cues=excerpts(cues);self.list.clear()
            for c in self.cues:
                item=QListWidgetItem(f"{core.clock(c['start'])} – {core.clock(c['end'])}\n{c.get('text','')}")
                self.list.addItem(item)
        self.setVisible(bool(cues))
    def follow(self,start,end=None):
        if not self.cues:return
        end=start if end is None else end
        # Prefer the greatest overlap with a selected range, then the nearest cue.
        def rank(i):
            c=self.cues[i];overlap=max(0,min(end,c['end'])-max(start,c['start']))
            distance=max(c['start']-end,start-c['end'],0)
            return (-overlap,distance,abs(c['start']-start))
        row=min(range(len(self.cues)),key=rank)
        if self.list.currentRow()!=row:
            self.list.setCurrentRow(row);self.list.scrollToItem(self.list.item(row),QAbstractItemView.ScrollHint.PositionAtCenter)
        self.caption.setText('Closest cue to selected range' if end!=start else 'Closest cue to playhead')
