"""Determinate per-stage progress for local scan jobs."""
import re
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QProgressBar,QPushButton

def measured_progress(text,duration):
    count=re.search(r'(Loading media|Scanning|Refining flagged scenes|Rendering segment|Preparing replacement)\s+(\d+)/(\d+)',text)
    if count:return count[1],int(count[2])/max(1,int(count[3]))*100
    seconds=re.search(r'(Analysing audio|Transcribing audio):\s*([\d.]+)s',text)
    if seconds and duration:return seconds[1],float(seconds[2])/duration*100
    percent=re.search(r'([\d.]+)%',text)
    if percent:return 'Model download',float(percent[1])
    return None

class CircleProgress(QWidget):
    def __init__(self):
        super().__init__();self.amount=0;self.setFixedSize(148,148)
    def setRange(self,a,b):pass
    def value(self):return self.amount
    def setValue(self,value):
        self.amount=max(0,min(100,value));self.setAccessibleName(f'Progress: {self.amount}%');self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);rect=QRectF(12,12,124,124)
        p.setPen(QPen(QColor('#303b48'),12));p.drawEllipse(rect)
        p.setPen(QPen(QColor('#67c5da'),12,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));p.drawArc(rect,90*16,-round(self.amount/100*360*16))
        p.setPen(QColor('#eef6ff'));font=p.font();font.setPointSize(23);font.setBold(True);p.setFont(font);p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,f'{self.amount}%')

class ScanProgress(QDialog):
    def __init__(self,parent,cancel,duration):
        super().__init__(parent);self.cancel_job=cancel;self.duration=duration;self.cancelling=False
        self.setWindowTitle('Operation progress');self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(460)
        layout=QVBoxLayout(self);self.stage=QLabel('Preparing - waiting for measurable work');layout.addWidget(self.stage)
        self.detail=QLabel('Starting...');self.detail.setWordWrap(True);layout.addWidget(self.detail)
        self.bar=CircleProgress();self.bar.setValue(0);layout.addWidget(self.bar,0,Qt.AlignmentFlag.AlignHCenter)
        note=QLabel('Percentage is for the current stage. Model loading may remain at 0% until processing begins.');note.setWordWrap(True);layout.addWidget(note)
        self.cancel_button=QPushButton('Cancel');self.cancel_button.clicked.connect(self.reject);layout.addWidget(self.cancel_button)
    def update_progress(self,text):
        if self.cancelling:return
        duration=re.fullmatch(r'Media duration: ([\d.]+)s',text)
        if duration:self.duration=float(duration[1]);return
        self.detail.setText(text)
        measured=measured_progress(text,self.duration)
        if measured:
            stage,value=measured;self.stage.setText(stage);self.bar.setValue(max(0,min(100,int(value))))
    def reject(self):
        if self.cancelling:return
        self.cancelling=True;self.cancel_button.setEnabled(False);self.detail.setText('Cancelling - waiting for the current operation to stop...');self.cancel_job()
