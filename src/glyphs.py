"""Font-independent media icons rendered locally."""
from PySide6.QtCore import Qt,QSize,QPointF,QRectF
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPolygonF,QColor,QPen,QPainterPath

def icon(name):
    pix=QPixmap(96,96);pix.fill(Qt.GlobalColor.transparent)
    p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.scale(4,4)
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#f2f6fa'))
    def triangle(points):p.drawPolygon(QPolygonF([QPointF(x,y) for x,y in points]))
    if name=='eye':
        shape=QPainterPath();shape.moveTo(1,12);shape.cubicTo(7,2,17,2,23,12);shape.cubicTo(17,22,7,22,1,12)
        p.setBrush(QColor('#edf6ff'));p.drawPath(shape);p.setBrush(QColor('#49b8d4'));p.drawEllipse(QRectF(6,6,12,12));p.setBrush(QColor('#132333'));p.drawEllipse(QRectF(9,9,6,6));p.setBrush(QColor('white'));p.drawEllipse(QRectF(13,8,3,3))
    elif name=='play':triangle([(7,4),(20,12),(7,20)])
    elif name=='pause':
        p.drawRoundedRect(QRectF(5,4,5,16),.6,.6);p.drawRoundedRect(QRectF(14,4,5,16),.6,.6)
    elif name in ('previous','next','frame-back','frame-next'):
        if name in ('previous','frame-back'):p.translate(24,0);p.scale(-1,1)
        triangle([(4,5),(15,12),(4,19)]);p.drawRect(QRectF(17,5,2,14))
        if name.startswith('frame'):
            p.setPen(QPen(QColor('#f2f6fa'),1));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(QRectF(1,2,22,20),2,2)
    elif name in ('drop','mature','person','pill','bug','speech','all'):
        p.setPen(QPen(QColor('#f2f6fa'),1.7));p.setBrush(Qt.BrushStyle.NoBrush)
        if name=='drop':
            triangle([(12,3),(5,14),(19,14)]);p.drawArc(QRectF(5,7,14,14),180*16,180*16)
        elif name=='mature':
            triangle([(12,3),(2,21),(22,21)]);p.drawLine(12,9,12,14);p.drawPoint(12,18)
        elif name=='person':
            p.drawEllipse(QRectF(9,2,6,6));p.drawLine(12,8,12,16);p.drawLine(5,11,19,11);p.drawLine(12,16,7,22);p.drawLine(12,16,17,22)
        elif name=='pill':
            p.translate(12,12);p.rotate(40);p.drawRoundedRect(QRectF(-5,-10,10,20),5,5);p.drawLine(-5,0,5,0)
        elif name=='bug':
            p.drawEllipse(QRectF(8,7,8,13));p.drawEllipse(QRectF(9,3,6,5))
            for y in (8,13,18):p.drawLine(3,y-2,8,y);p.drawLine(16,y,21,y-2)
        elif name=='speech':
            p.drawRoundedRect(QRectF(3,3,18,14),3,3);p.drawLine(7,17,5,22);p.drawLine(5,22,13,17);p.drawLine(7,8,17,8);p.drawLine(7,12,14,12)
        else:
            for x in (4,14):
                for y in (4,14):p.drawRoundedRect(QRectF(x,y,6,6),1,1)
    else:
        p.setPen(QPen(QColor('#f2f6fa'),2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        if name in ('plus','minus'):
            p.drawLine(5,12,19,12)
            if name=='plus':p.drawLine(12,5,12,19)
        elif name=='fit':
            for x,y,dx,dy in [(4,4,1,1),(20,4,-1,1),(4,20,1,-1),(20,20,-1,-1)]:
                p.drawLine(x,y,x+5*dx,y);p.drawLine(x,y,x,y+5*dy)
    p.end();return QIcon(pix)

def set_glyph(button,name,label,only=True,size=20):
    button.setIcon(icon(name));button.setIconSize(QSize(size,size))
    if only:button.setText('')
    button.setToolTip(label);button.setAccessibleName(label)
