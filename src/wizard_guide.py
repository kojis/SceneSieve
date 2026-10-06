"""Nonmodal, anchored hints after the guided scans finish."""
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton

class ReviewGuide(QDialog):
    def __init__(self,window):
        super().__init__(window,Qt.WindowType.Tool)
        self.w=window;self.step=0
        self.setWindowTitle('Wizard guide');self.setFixedWidth(340)
        layout=QVBoxLayout(self)
        self.heading=QLabel();self.heading.setStyleSheet('font-weight:600;font-size:16px');layout.addWidget(self.heading)
        self.copy=QLabel();self.copy.setWordWrap(True);layout.addWidget(self.copy)
        self.next_button=QPushButton('Got it');self.next_button.clicked.connect(self.advance);layout.addWidget(self.next_button)
        self.timer=QTimer(self);self.timer.timeout.connect(self.position);self.timer.start(150)
        self.present()
    def present(self):
        if self.step==0:
            self.anchor=self.w.docks['Findings'];self.anchor.show();self.anchor.raise_()
            self.heading.setText('Review findings')
            self.copy.setText('You can review the Findings table now if desired. Select a range to preview it, adjust its boundaries, or disable a filter you want to keep. Detection may miss content or flag harmless scenes.')
        else:
            dock=self.w.docks['Detection and export'];dock.show();dock.raise_()
            self.anchor=self.w.editor_tabs.tabBar()
            self.heading.setText('Export when you are ready')
            self.copy.setText('When you finish reviewing the removals, go to the Export tab to export the edited video with filters, or save a filter file compatible with another media player.')
        self.adjustSize();self.position()
    def position(self):
        rect=self.anchor.rect() if self.step==0 else self.anchor.tabRect(2)
        point=self.anchor.mapToGlobal(rect.center())
        screen=self.anchor.screen().availableGeometry()
        x=self.anchor.mapToGlobal(rect.topRight()).x()+12
        if x+self.width()>screen.right():x=self.anchor.mapToGlobal(rect.topLeft()).x()-self.width()-12
        x=max(screen.left(),min(x,screen.right()-self.width()))
        y=max(screen.top(),min(point.y()-self.height()//2,screen.bottom()-self.height()))
        self.move(QPoint(x,y))
        direction='→' if x<point.x() else '←'
        self.heading.setText(direction+(' Review findings' if self.step==0 else ' Export tab'))
    def advance(self):
        if self.step==0:self.step=1;self.present()
        else:self.accept()
    def done(self,result):
        self.timer.stop();super().done(result)
