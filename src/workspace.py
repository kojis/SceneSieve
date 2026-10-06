"""Rearrangeable editor panels using Qt's native dock controls."""

from PySide6.QtCore import Qt,QByteArray

from PySide6.QtWidgets import QMainWindow,QDockWidget,QWidget,QVBoxLayout,QScrollArea,QPushButton



def install(window,playback,transport,marking,wave_row,findings,edits,preview):

    host=QMainWindow();host.setDockNestingEnabled(True)

    host.setDockOptions(QMainWindow.DockOption.AllowNestedDocks|QMainWindow.DockOption.AnimatedDocks)

    center=QWidget();center.setMaximumSize(0,0);host.setCentralWidget(center)

    # Reparent the regions before disposing of the old splitter layout.

    video=QWidget();v=QVBoxLayout(video);v.setContentsMargins(0,0,0,0);v.addWidget(window.surface)

    video.installEventFilter(window.video_overlay.click_filter)
    playback.layout().removeItem(transport);v.addLayout(transport)

    timeline=QWidget();t=QVBoxLayout(timeline);t.setContentsMargins(0,0,0,0);t.setSpacing(6)
    marking.setSpacing(4);marking.setContentsMargins(0,0,0,0);wave_row.setContentsMargins(0,0,0,0)
    for i in range(marking.count()):
        widget=marking.itemAt(i).widget()
        if isinstance(widget,QPushButton):widget.setStyleSheet("QPushButton{padding:3px 8px}")

    playback.layout().removeItem(marking);t.addLayout(marking)

    playback.layout().removeItem(wave_row);t.addLayout(wave_row)

    preview_scroll=QScrollArea();preview_scroll.setWidgetResizable(True);preview_scroll.setWidget(preview)
    results=QWidget();r=QVBoxLayout(results);r.setContentsMargins(0,0,0,0);r.addWidget(window.table)

    findings.removeItem(edits);r.addLayout(edits)

    window.content.layout().addWidget(host)

    window.dock_host=host;window.docks={}

    for name,widget in [('Player',video),('Timeline',timeline),('Findings',results),('Preview and edit',preview_scroll),('Detection and export',window.editor_tabs),('Subtitles',window.subtitle_sidebar)]:

        dock=QDockWidget(name,host);dock.setObjectName('dock-'+name);dock.setWidget(widget)

        host.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea,dock);window.docks[name]=dock

    d=window.docks

    host.splitDockWidget(d['Player'],d['Subtitles'],Qt.Orientation.Horizontal)

    host.splitDockWidget(d['Player'],d['Timeline'],Qt.Orientation.Vertical)

    host.splitDockWidget(d['Timeline'],d['Findings'],Qt.Orientation.Vertical)

    host.splitDockWidget(d['Findings'],d['Preview and edit'],Qt.Orientation.Horizontal)

    host.splitDockWidget(d['Player'],d['Detection and export'],Qt.Orientation.Horizontal)
    d['Findings'].setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable|QDockWidget.DockWidgetFeature.DockWidgetFloatable)
    d['Findings'].toggleViewAction().setEnabled(False)

    host.resizeDocks([d['Player'],d['Timeline'],d['Findings']],[280,200,270],Qt.Orientation.Vertical)

    d['Subtitles'].hide()

    window.workspace_splitter.hide();window.workspace_splitter.setParent(None);window.workspace_splitter.deleteLater()

    window.default_dock_state=host.saveState()

    files=window.menuBar().addMenu('&File')

    for label,callback in [('Open video…',window.open_video),('Load scenes…',window.load_scenes),('Save scenes…',window.save_scenes),('Export player file…',window.export)]:files.addAction(label,callback)

    files.addSeparator();files.addAction('Exit',window.close)

    panels=window.menuBar().addMenu('&View');layout=window.menuBar().addMenu('&Layout')

    for name,dock in d.items():
        if name!='Findings':panels.addAction(dock.toggleViewAction())

    layout.addAction('Save layout',window.save_layout)

    layout.addAction('Reset layout',lambda:host.restoreState(window.default_dock_state))

    lock=layout.addAction('Lock panels');lock.setCheckable(True)

    lock.toggled.connect(lambda checked:[dock.setFeatures((QDockWidget.DockWidgetFeature.NoDockWidgetFeatures if dock is d['Findings'] else QDockWidget.DockWidgetFeature.DockWidgetClosable) if checked else ((QDockWidget.DockWidgetFeature.NoDockWidgetFeatures if dock is d['Findings'] else QDockWidget.DockWidgetFeature.DockWidgetClosable)|QDockWidget.DockWidgetFeature.DockWidgetMovable|QDockWidget.DockWidgetFeature.DockWidgetFloatable)) for dock in d.values()])

    if window.settings.get('dock_layout_v35'):

        host.restoreState(QByteArray.fromBase64(window.settings['dock_layout_v35'].encode()))


    d['Findings'].show();d['Findings'].raise_()
