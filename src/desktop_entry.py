"""Frozen Windows entry point with automatic offline AI startup."""
import json
import sys
import traceback
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
import local_ai
from paths import DATA, ROOT, BIN

def self_test(output):
    import subprocess
    import time
    import tempfile
    import numpy as np
    import cv2
    import core
    import scanner
    from app import Window
    models=scanner.local_models()
    assert models,models
    model='qwen3-vl:2b' if 'qwen3-vl:2b' in models else models[0]
    import shutil,os
    executable=str(BIN/'mpv.exe') if os.name=='nt' else shutil.which('mpv')
    assert executable
    player=subprocess.run([executable,'--version'],capture_output=True,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,timeout=20)
    assert player.returncode==0
    window=Window()
    assert window.strict_gore.isChecked()
    assert window.labels()==set()
    window.categories.setText('gore')
    frame=np.full((192,320,3),(40,160,40),dtype=np.uint8)
    labels=scanner.classify(frame,model,['gore'])
    assert labels==[],labels
    errors=[];window.embedded.failed.connect(errors.append)
    with tempfile.TemporaryDirectory(prefix='scenesieve-test-') as folder:
        video=Path(folder)/'clip.mp4'
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),24,(320,192))
        for _ in range(48):writer.write(frame)
        writer.release()
        window.video=str(video)
        window.doc={'version':1,'duration':2.,'video':video.name,'fingerprint':core.fingerprint(video),'scenes':[]}
        window.refresh();window.load_embedded(paused=True)
        def wait_for(condition):
            limit=time.monotonic()+15
            while time.monotonic()<limit:
                QApplication.processEvents();time.sleep(.01)
                if errors:raise RuntimeError(errors)
                if condition():return
            raise RuntimeError('Embedded playback test timed out.')
        wait_for(lambda:window.embedded.ready and not window.embedded.loading)
        window.embedded.seek(.5);wait_for(lambda:abs(window.source_position-.5)<.04)
        window.jog_frame(1);wait_for(lambda:window.source_position>.52)
        window.select_range(.5,1.);window.commit_range()
        assert len(window.doc['scenes'])==1
        window.filtered.setChecked(True);wait_for(lambda:not window.embedded.loading)
        window.embedded.seek(.75);wait_for(lambda:window.source_position>=1.)
        window.dirty=False
        window.embedded.close()
    window.close()
    Path(output).write_text(json.dumps({'status':'passed','frozen':bool(getattr(sys,'frozen',False)),
        'models':models,'mpv':True,'qt':True,'embedded_player':True,'timeline_marking':True,
        'local_inference':True,'default_filters':[]}),encoding='utf-8')

def main():
    application=QApplication(sys.argv);application.setStyle('Fusion')
    from glyphs import icon
    application.setWindowIcon(icon('eye'))
    DATA.mkdir(parents=True,exist_ok=True)
    try:
        if '--self-test' in sys.argv:
            local_ai.start()
            self_test(sys.argv[sys.argv.index('--self-test')+1])
            return 0
        from app import Window
        from launch_ui import LaunchDialog,SetupWizard,start_mode
        window=Window();application.setQuitOnLastWindowClosed(False)
        plan=None
        while True:
            chooser=LaunchDialog(window)
            if not chooser.exec():return 0
            if chooser.choice!='Wizard':break
            wizard=SetupWizard(window,chooser.path)
            if wizard.exec():plan=wizard.plan();break
        window.show();application.setQuitOnLastWindowClosed(True)
        window.status.setText('Starting the local AI service…')
        def ready(models):
            window.populate_models(models)
            window.status.setText('Ready. Models download when Scan is selected. Processing stays local.')
        def startup(progress):
            progress('Preparing local services before loading media…')
            local_ai.start()
            if window.cancel.is_set():raise InterruptedError('Startup cancelled.')
            import models
            return models.catalog(not (DATA/'vision-catalog.json').exists())
        def initialize():
            window.run_job(startup,ready,True)
            window.worker.finished.connect(lambda:QTimer.singleShot(0,lambda:start_mode(window,chooser.choice,chooser.path,plan) if not window.cancel.is_set() else None))
        QTimer.singleShot(0,initialize)
        return application.exec()
    except Exception:
        report=traceback.format_exc()
        (DATA/'startup-error.txt').write_text(report,encoding='utf-8')
        if '--self-test' not in sys.argv:
            QMessageBox.critical(None,'SceneSieve could not start',report.splitlines()[-1]+'\nDetails: '+str(DATA/'startup-error.txt'))
        return 1
    finally:
        local_ai.stop()

if __name__=='__main__':sys.exit(main())
