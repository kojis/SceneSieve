"""Embedded mpv with asynchronous JSON IPC and source-time mapping."""
import json
import os
import sys
import tempfile
import uuid
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket

def source_time(position, ranges):
    cursor=0.0
    for start,end in ranges:
        if position < cursor+end-start:
            return start+max(0,position-cursor)
        cursor+=end-start
    return ranges[-1][1] if ranges else 0.0

def playback_time(position, ranges):
    cursor=0.0
    for start,end in ranges:
        if position < start:return cursor
        if position < end:return cursor+position-start
        cursor+=end-start
    return max(0,cursor-.001)

class EmbeddedPlayer(QObject):
    positionChanged=Signal(float)
    pausedChanged=Signal(bool)
    failed=Signal(str)
    loaded=Signal()
    keyPressed=Signal(str)
    seekSettled=Signal(float)
    def __init__(self,surface,parent=None):
        super().__init__(parent)
        self.surface=surface;self.process=QProcess(self);self.socket=QLocalSocket(self)
        self.timer=QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.connect_pipe)
        self.socket.connected.connect(self.connected);self.socket.readyRead.connect(self.read)
        self.process.errorOccurred.connect(lambda _:self.failed.emit('The embedded player could not start.'))
        self.process.finished.connect(self.exited)
        self.seek_pending=False
        self.command_serial=1000;self.checked_commands={}
        self.buffer=b'';self.pending=None;self.ranges=[];self.paused=True;self.position=0.;self.ready=False
        self.audio_path=None;self.loading=False;self.after_load=[];self.tries=0;self.closing=False;self.input_path=None
    def start(self,executable):
        if self.process.state()!=QProcess.ProcessState.NotRunning:return
        name='scenesieve-'+uuid.uuid4().hex
        bindings={'DEL':'delete','UP':'gain-up','DOWN':'gain-down','Shift+UP':'gain-fine-up','Shift+DOWN':'gain-fine-down','SPACE':'space','LEFT':'left','RIGHT':'right','Ctrl+LEFT':'back','Ctrl+RIGHT':'forward',
                  ',':'left','.':'right','i':'in','o':'out','m':'mark','[':'previous',']':'next',
                  '+':'zoom-in','=':'zoom-in','-':'zoom-out','MOUSE_BTN0':'focus'}
        with tempfile.NamedTemporaryFile(mode='w',suffix='.conf',prefix='scenesieve-input-',delete=False) as f:
            f.write(''.join(key+' script-message scenesieve-key '+action+'\n' for key,action in bindings.items()))
            self.input_path=f.name
        self.pipe='\\\\.\\pipe\\'+name if os.name=='nt' else os.path.join(tempfile.gettempdir(),name)
        self.process.setProgram(executable)
        self.process.setArguments(['--no-config','--load-scripts=no','--idle=yes','--keep-open=yes',
            '--force-window=yes','--volume-max=150','--terminal=no','--osc=no','--input-default-bindings=no',
            '--input-vo-keyboard=yes','--input-cursor=yes','--input-conf='+self.input_path,'--no-resume-playback',
            *(['--title=SceneSieve Preview'] if sys.platform=='darwin' else ['--wid='+str(int(self.surface.winId()))]),'--input-ipc-server='+self.pipe])
        self.process.start();self.tries=0;self.timer.start()
    def connect_pipe(self):
        self.tries+=1
        if self.tries>100:
            self.timer.stop();self.failed.emit('Could not connect to the embedded player.');return
        if self.socket.state()==QLocalSocket.LocalSocketState.UnconnectedState:
            self.socket.connectToServer(self.pipe)
    def connected(self):
        self.timer.stop();self.ready=True
        self.command('observe_property',1,'time-pos');self.command('observe_property',2,'pause')
        if self.pending:
            args=self.pending;self.pending=None;self.load(*args)
    def command(self,*args):
        if self.ready:
            payload={'command':list(args)}
            if args[:2]==('set_property','af'):
                self.command_serial+=1;payload['request_id']=self.command_serial;self.checked_commands[self.command_serial]='Audio filter'
            self.socket.write((json.dumps(payload)+'\n').encode())
    def load(self,path,ranges,position=0.,paused=True,audio_path=None,rendered=False):
        if not self.ready:
            self.pending=(path,ranges,position,paused,audio_path,rendered);return
        self.rendered=rendered;self.audio_path=audio_path
        self.ranges=list(ranges);self.position=position;self.paused=paused;self.loading=True
        self.after_load=[]
        self.command('set_property','pause',True)
        self.command('set_property','af','')
        options={'start':str(playback_time(position,self.ranges)),'pause':'yes'}
        if audio_path:options['audio-files']=str(audio_path)
        if os.name=='nt':self.command('loadfile',str(path),'replace',-1,options)
        else:
            if audio_path:self.command('set_property','audio-files',str(audio_path))
            else:self.command('set_property','audio-files','')
            self.command('loadfile',str(path),'replace')
    def read(self):
        self.buffer+=bytes(self.socket.readAll())
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('event')=='seek':self.seek_pending=True
            if event.get('event')=='playback-restart' and self.seek_pending:
                self.seek_pending=False
                if self.ready:self.socket.write((json.dumps({'command':['get_property','time-pos'],'request_id':999})+'\n').encode())
            if event.get('request_id')==999 and event.get('error')=='success' and isinstance(event.get('data'),(int,float)):
                self.seekSettled.emit(source_time(event['data'],self.ranges))
            checked=self.checked_commands.pop(event.get('request_id'),None)
            if checked and event.get('error') not in (None,'success'):
                self.pause();self.failed.emit(checked+' could not be applied: '+str(event['error']))
            if event.get('event')=='file-loaded':
                self.loading=False
                if os.name!='nt':self.command('seek',playback_time(self.position,self.ranges),'absolute+exact')
                self.loaded.emit()
                self.command('set_property','pause',self.paused)
                queued=self.after_load;self.after_load=[]
                for action in queued:action()
            elif event.get('event')=='property-change' and not self.loading:
                if event.get('name')=='time-pos' and event.get('data') is not None:
                    self.position=source_time(float(event['data']),self.ranges)
                    self.positionChanged.emit(self.position)
                elif event.get('name')=='pause' and event.get('data') is not None:
                    self.paused=bool(event['data']);self.pausedChanged.emit(self.paused)
            elif event.get('event')=='end-file' and event.get('reason')=='error':
                self.loading=False;self.failed.emit('Cannot play this media: '+event.get('file_error','unknown playback error'))
            elif event.get('event')=='client-message':
                args=event.get('args',[])
                if len(args)==2 and args[0]=='scenesieve-key':self.keyPressed.emit(args[1])
    def seek(self,position):
        if self.loading:self.after_load.append(lambda:self.seek(position));return
        self.command('seek',playback_time(position,self.ranges),'absolute+exact')
    def pause(self,value=True):
        self.paused=value
        if self.loading:self.after_load.append(lambda:self.pause(value));return
        self.command('set_property','pause',value)
    def step(self,direction):
        if self.loading:self.after_load.append(lambda:self.step(direction));return
        self.command('frame-step' if direction>0 else 'frame-back-step')
    def exited(self,code,status):
        self.ready=False;self.timer.stop();self.socket.abort()
        if not self.closing and code:
            self.failed.emit('Embedded player exited: '+bytes(self.process.readAllStandardError()).decode(errors='replace')[-500:])
    def close(self):
        self.closing=True;self.timer.stop();self.command('quit');self.socket.flush()
        if self.process.state()!=QProcess.ProcessState.NotRunning and not self.process.waitForFinished(1500):
            self.process.terminate()
            if not self.process.waitForFinished(1000):self.process.kill();self.process.waitForFinished(1000)
        self.socket.abort()
        if self.input_path:
            try:os.unlink(self.input_path)
            except OSError:pass
