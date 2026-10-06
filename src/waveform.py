"""Waveform sharing the editor timeline's viewport and seeking."""
import math
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import QWidget
class Waveform(QWidget):
    def __init__(self,timeline):
        super().__init__();self.timeline=timeline;self.data={'step':.05,'peak':[],'rms':[]};self.setMinimumHeight(58);self.setMaximumHeight(75)
        self.setToolTip('Audio waveform • click to seek • wheel to zoom with timeline')
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#142833'));mid=self.height()/2;p.setPen(QColor('#5cc2c6'))
        peaks=self.data['peak'];step=self.data['step'];t=self.timeline
        if not peaks:p.drawText(8,25,'Audio waveform — analysing audio or no audio track');return
        for x in range(self.width()):
            a=max(0,int((t.left+x/max(1,self.width())*t.span)/step));b=min(len(peaks),max(a+1,int((t.left+(x+1)/max(1,self.width())*t.span)/step)))
            height=min(1,max(peaks[a:b],default=0))*(mid-5);p.drawLine(x,int(mid-height),x,int(mid+height))
        p.setPen(QPen(QColor('white'),2));x=int((t.position-t.left)/t.span*self.width());p.drawLine(x,0,x,self.height())
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:self.timeline.seekRequested.emit(self.timeline.time_at(e.position().x()))
    def wheelEvent(self,e):self.timeline.wheelEvent(e);self.update()
