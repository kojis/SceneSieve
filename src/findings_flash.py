"""Brief highlights for new or changed findings, including selected rows."""
import json,time
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyledItemDelegate

class FindingsFlash(QStyledItemDelegate):
    def __init__(self,table):
        super().__init__(table);self.table=table;self.previous={};self.until={}
        self.timer=QTimer(self);self.timer.setInterval(80);self.timer.timeout.connect(self.tick)
    def update_scenes(self,scenes):
        current={};now=time.monotonic()
        for row,scene in enumerate(scenes):
            key=(scene['start'],scene['end'],scene.get('source'),scene.get('category'))
            value=json.dumps(scene,sort_keys=True);current[key]=value
            if self.previous.get(key)!=value:self.until[row]=now+1.1
        self.previous=current
        if self.until:self.timer.start();self.table.viewport().update()
    def tick(self):
        self.until={row:end for row,end in self.until.items() if end>time.monotonic()}
        self.table.viewport().update()
        if not self.until:self.timer.stop()
    def paint(self,painter,option,index):
        super().paint(painter,option,index)
        remaining=self.until.get(index.row(),0)-time.monotonic()
        if remaining>0:
            painter.save();painter.fillRect(option.rect,QColor(255,210,40,round(85*min(1,remaining))));painter.restore()
