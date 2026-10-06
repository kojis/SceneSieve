"""Zoomable original-video timeline with scene selection and boundary handles."""
import math
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget,QApplication
import core

class Timeline(QWidget):
    seekRequested=Signal(float)
    sceneSelected=Signal(int)
    boundaryChanged=Signal(int,float,float)
    rangeSelected=Signal(float,float)
    gainChanged=Signal(int,float)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150);self.setMaximumHeight(180);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.duration=0.;self.left=0.;self.span=1.;self.position=0.;self.scenes=[];self.active=set();self.selected=-1
        self.selected_rows=set();self.pending=None;self.drag=None;self.selection=None
        self.data={'step':.05,'peak':[],'rms':[]}
        self.gain_preview=None
        self.setToolTip('Click to seek • click a range to select • drag its edges to trim • drag to select a new range • drag a gain line vertically to change dB • wheel to zoom • Shift-wheel to pan')
    def set_data(self,duration,scenes,active):
        reset=duration!=self.duration;self.duration=duration;self.scenes=scenes;self.active=active
        if reset:self.fit()
        self.selected=min(self.selected,len(scenes)-1);self.update()
    def fit(self):self.left=0.;self.span=max(.04,self.duration);self.update()
    def time_at(self,x):return max(0,min(self.duration,self.left+x/max(1,self.width())*self.span))
    def graph_bottom(self):return self.height()-max(22,self.fontMetrics().height()+8)
    def virtual_gain_range(self):
        if self.selection and self.selection[0]!=self.selection[1]:
            target=tuple(sorted(self.selection))
            if any(s.get('action')=='gain' and abs(s['start']-target[0])<.001 and abs(s['end']-target[1])<.001 for s in self.scenes):return None
            return target
        if 0<=self.selected<len(self.scenes):
            scene=self.scenes[self.selected]
            if scene.get('action')!='gain':return scene['start'],scene['end']
        if any(s.get('action')=='gain' and s['start']==0 and s['end']==self.duration for s in self.scenes):return None
        return (0,self.duration) if self.duration else None
    def gain_y(self,db):
        middle=(30+self.graph_bottom()-4)/2;half=middle-30
        db=max(-60,min(12,db))
        return middle-db/(12 if db>=0 else 60)*half
    def gain_at(self,y):
        middle=(30+self.graph_bottom()-4)/2;half=middle-30
        return round(max(-60,min(12,(middle-y)/half*(12 if y<=middle else 60))),1)
    def x_at(self,t):return (t-self.left)/self.span*self.width()
    def zoom(self,factor,anchor=None):
        anchor=self.position if anchor is None else anchor
        ratio=max(0,min(1,(anchor-self.left)/self.span))
        self.span=max(min(.1,self.duration),min(max(.1,self.duration),self.span/factor))
        self.left=max(0,min(max(0,self.duration-self.span),anchor-ratio*self.span));self.update()
    def set_position(self,t):
        self.position=t;self.update()
    def ensure_visible(self,t):
        if t<self.left or t>self.left+self.span:
            self.left=max(0,min(max(0,self.duration-self.span),t-self.span/2));self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#15191f'))
        bottom=self.graph_bottom();middle=(26+bottom)/2
        p.fillRect(QRectF(0,24,self.width(),bottom-24),QColor('#1c252c'))
        p.setPen(QColor('#9bb1bf'))
        ideal=self.span/8;step=10**math.floor(math.log10(max(.001,ideal)))
        step*=next((n for n in [1,2,5,10] if n*step>=ideal),10)
        t=math.ceil(self.left/step)*step
        while t<=min(self.duration,self.left+self.span):
            x=self.x_at(t);p.drawLine(int(x),0,int(x),18);p.drawText(int(x)+3,15,core.clock(t));t+=step
        peaks=self.data['peak'];step=self.data['step'];p.setPen(QColor('#5cc2c6'))
        for x in range(self.width()):
            a=max(0,int((self.left+x/max(1,self.width())*self.span)/step));b=min(len(peaks),max(a+1,int((self.left+(x+1)/max(1,self.width())*self.span)/step)))
            height=min(1,max(peaks[a:b],default=0))*(bottom-30)/2;p.drawLine(x,int(middle-height),x,int(middle+height))
        for i,s in enumerate(self.scenes):
            a,b=self.x_at(s['start']),self.x_at(s['end'])
            if b<0 or a>self.width():continue
            color=('#69b4cf' if s.get('action') in ('duck','bleep','replace') else '#ad98d6' if s.get('action')=='gain' else '#d56e61') if s['enabled'] and (s.get('action')!='skip' or s['category'] in self.active) else '#405362'
            tint=QColor(color);tint.setAlpha(45 if s.get('action')=='gain' else 80);p.fillRect(QRectF(a,26,max(3,b-a),bottom-26),tint)
            if i==self.selected or i in self.selected_rows:
                p.setPen(QPen(QColor('#ffe4aa'),2));p.drawRect(QRectF(a,25,max(3,b-a),bottom-25))
                p.fillRect(QRectF(a-3,24,6,bottom-24),QColor('#ffe4aa'));p.fillRect(QRectF(b-3,24,6,bottom-24),QColor('#ffe4aa'))
        if self.selection:
            a,b=sorted(self.selection);p.fillRect(QRectF(self.x_at(a),bottom+3,max(2,self.x_at(b)-self.x_at(a)),6),QColor('#62b9c8'))
        if self.pending is not None:
            p.setPen(QPen(QColor('#62b9c8'),2));x=int(self.x_at(self.pending));p.drawLine(x,20,x,bottom)
        p.setPen(QPen(QColor('#ffffff'),2));x=int(self.x_at(self.position));p.drawLine(x,18,x,bottom)
        for db in (12,0,-24,-60):
            y=self.gain_y(db);p.setPen(QPen(QColor('#353b48'),1,Qt.PenStyle.DashLine));p.drawLine(0,int(y),self.width(),int(y))
            p.setPen(QColor('#8a96a9'));p.drawText(self.width()-self.fontMetrics().horizontalAdvance(f'{db:+} dB')-6,int(y)-2,f'{db:+} dB')
        for i,s in enumerate(self.scenes):
            if s.get('action')!='gain':continue
            a=max(0,self.x_at(s['start']));b=min(self.width(),self.x_at(s['end']))
            if b<a:continue
            db=self.gain_preview[1] if self.gain_preview and self.gain_preview[0]==i else s.get('gain_db',0)
            y=self.gain_y(db);color=QColor('#c5adff' if s['enabled'] else '#687080')
            p.setPen(QPen(color,3 if i in self.selected_rows or i==self.selected else 2));p.drawLine(int(a),int(y),int(b),int(y))
            p.setBrush(color);p.drawEllipse(QRectF((a+b)/2-4,y-4,8,8))
            if b-a>65:p.drawText(int(a)+6,int(y)-6,f'{db:+.1f} dB')
        target=self.virtual_gain_range()
        if target:
            a,b=map(self.x_at,target);db=self.gain_preview[1] if self.gain_preview and self.gain_preview[0]==-1 else 0
            y=self.gain_y(db);p.setPen(QPen(QColor('#c5adff'),2));p.drawLine(int(a),int(y),int(b),int(y))
            p.drawText(int(max(0,a))+8,int(y)-6,f'{db:+.1f} dB • drag to adjust gain');p.setBrush(QColor('#c5adff'));p.drawEllipse(QRectF((a+b)/2-4,y-4,8,8))
        p.setPen(QColor('#939eaf'));p.drawText(6,self.height()-5,'AUDIO / GAIN • drag purple lines vertically to adjust dB • waveform shows source audio')
        p.setPen(QPen(QColor('#f1c56c'),1));x=int(self.x_at(self.position));p.drawLine(x,18,x,bottom)
    def mousePressEvent(self,event):
        if not self.duration or event.button()!=Qt.MouseButton.LeftButton:return
        self.setFocus();t=self.time_at(event.position().x())
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.drag=('selection',t);self.selection=(t,t);self.update();return
        if 0<=self.selected<len(self.scenes):
            s=self.scenes[self.selected]
            for edge in ('start','end'):
                if abs(self.x_at(s[edge])-event.position().x())<=7 and 23<=event.position().y()<=self.graph_bottom():
                    self.drag=(edge,self.selected);self.selection=(s['start'],s['end']);return
        for i in reversed(range(len(self.scenes))):
            s=self.scenes[i]
            if s.get('action')=='gain' and s['start']<=t<=s['end'] and abs(event.position().y()-self.gain_y(s.get('gain_db',0)))<=9:
                self.selected=i;self.sceneSelected.emit(i);self.drag=('gain',i,t,event.position().x(),event.position().y());self.gain_preview=(i,s.get('gain_db',0));self.update();return
        target=self.virtual_gain_range()
        if target and target[0]<=t<=target[1] and abs(event.position().y()-self.gain_y(0))<=9:
            self.drag=('gain',-1,t,event.position().x(),event.position().y());self.gain_preview=(-1,0);self.update();return
        self.selection=None;self.drag=('pending',t,event.position().x(),event.position().y());self.update()
    def mouseMoveEvent(self,event):
        if not self.drag:return
        t=self.time_at(event.position().x());kind=self.drag[0]
        if kind=='pending':
            if abs(event.position().x()-self.drag[2])>=QApplication.startDragDistance():self.drag=('selection',self.drag[1]);self.selection=(self.drag[1],t)
        elif kind=='gain':
            dx=abs(event.position().x()-self.drag[3]);dy=abs(event.position().y()-self.drag[4])
            if dx>=QApplication.startDragDistance() and dx>dy:self.drag=('selection',self.drag[2]);self.gain_preview=None;self.selection=(self.drag[1],t)
            else:self.gain_preview=(self.drag[1],self.gain_at(event.position().y()))
        elif kind=='scrub':self.seekRequested.emit(t)
        elif kind=='selection':self.selection=(self.drag[1],t)
        else:
            s=self.scenes[self.drag[1]]
            self.selection=(min(t,s['end']-.001),s['end']) if kind=='start' else (s['start'],max(t,s['start']+.001))
        self.update()
    def mouseReleaseEvent(self,event):
        if not self.drag:return
        if self.drag[0]=='pending':
            t=self.time_at(event.position().x())
            if 26<=event.position().y()<=self.graph_bottom():
                hits=[i for i,s in enumerate(self.scenes) if s['start']<=t<=s['end']]
                if hits:self.selected=hits[-1];self.sceneSelected.emit(self.selected)
            self.seekRequested.emit(t)
        elif self.drag[0]=='gain':
            self.gainChanged.emit(self.drag[1],self.gain_at(event.position().y()));self.gain_preview=None
        elif self.drag[0]=='selection' and self.selection:
            a,b=sorted(self.selection)
            if b>a:self.rangeSelected.emit(a,b)
        elif self.drag[0] in ('start','end'):
            self.boundaryChanged.emit(self.drag[1],*self.selection);self.selection=None
        self.drag=None;self.update()
    def wheelEvent(self,event):
        if not self.duration:return
        delta=event.angleDelta().y() or event.angleDelta().x()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.left=max(0,min(max(0,self.duration-self.span),self.left-delta/120*self.span*.1));self.update()
        else:self.zoom(1.25**(delta/120),self.time_at(event.position().x()))
        event.accept()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.selection=(0,self.duration);self.rangeSelected.emit(0,self.duration);self.update();event.accept();return
        super().keyPressEvent(event)
