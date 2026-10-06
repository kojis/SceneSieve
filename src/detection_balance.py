"""Detection tradeoff control; preference levels are not confidence scores."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QSlider
class DetectionBalance(QWidget):
    def __init__(self):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.caption=QLabel();layout.addWidget(self.caption)
        row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel('Broader filtering'))
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(0,4);self.slider.setValue(4);self.slider.setTickInterval(1);self.slider.setTickPosition(QSlider.TickPosition.TicksBelow);self.slider.setAccessibleName('Detection precision balance');row.addWidget(self.slider);row.addWidget(QLabel('More precise'))
        self.slider.valueChanged.connect(self.update_caption);self.update_caption()
        self.setToolTip('Applies to the next scan. Broader filtering includes uncertain matches; greater precision requires clearer evidence and uses confirmation passes. These are preferences, not calibrated confidence scores.')
    def value(self):return self.slider.value()*25
    def setValue(self,value):self.slider.setValue(round(value/25))
    def update_caption(self):self.caption.setText('Detection balance: '+['Most inclusive','Inclusive','Balanced','Precise','Most precise'][self.slider.value()])
