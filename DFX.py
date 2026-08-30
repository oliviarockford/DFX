import sys,time,threading,queue,socket,json
from collections import deque
from pathlib import Path
import numpy as np
import sounddevice as sd
from PySide6 import QtCore,QtGui,QtWidgets
import dfx_core_v050 as dfx
from native_decoder import NativeDecoder

APP=Path.home()/'.dfx'; APP.mkdir(exist_ok=True)
SETTINGS=APP/'settings.json'; ADIF=APP/'dfx_log.adi'

class Rig:
    def __init__(self): self.mode='None';self.ser=None;self.host='127.0.0.1';self.port=4532
    def configure(self,mode,serial_port='',host='127.0.0.1',port=4532):
        self.close();self.mode=mode;self.host=host;self.port=int(port)
        if mode=='Serial RTS':
            import serial;self.ser=serial.Serial(serial_port,9600,timeout=.2);self.ser.rts=False
    def cmd(self,s):
        with socket.create_connection((self.host,self.port),timeout=1.5) as x:
            x.sendall((s+'\n').encode());return x.recv(1024)
    def ptt(self,on):
        if self.mode=='Serial RTS' and self.ser:self.ser.rts=bool(on)
        elif self.mode=='Hamlib rigctld':self.cmd(f'T {1 if on else 0}')
    def close(self):
        if self.ser:
            try:self.ser.close()
            except:pass
        self.ser=None

class Waterfall(QtWidgets.QWidget):
    def __init__(self):super().__init__();self.lines=deque(maxlen=120);self.setMinimumHeight(180)
    def add(self,s):self.lines.append(np.asarray(s));self.update()
    def paintEvent(self,e):
        p=QtGui.QPainter(self);p.fillRect(self.rect(),QtGui.QColor('black'))
        if not self.lines:return
        w,h=self.width(),self.height(); ls=list(self.lines)
        for y in range(h):
            k=len(ls)-1-int(y*len(ls)/max(1,h))
            if k<0:continue
            a=ls[k];lo=np.percentile(a,25);hi=np.percentile(a,99);den=max(1e-6,hi-lo)
            for x in range(w):
                v=float(np.clip((a[min(len(a)-1,int(x*len(a)/w))]-lo)/den,0,1));c=QtGui.QColor.fromHsvF((.66-.66*v),1,min(1,.25+v));p.setPen(c);p.drawPoint(x,y)

class Engine(QtCore.QObject):
    decoded=QtCore.Signal(dict);snr=QtCore.Signal(float);spec=QtCore.Signal(object);status=QtCore.Signal(str)
    def __init__(self,rig):
        super().__init__();self.rig=rig;self.running=False;self.q=queue.Queue();self.buf=deque(maxlen=dfx.FS*35);self.stream=None;self.inp=None;self.out=None;self.decoder=NativeDecoder()
    def start(self):
        if self.running:return
        self.running=True;threading.Thread(target=self.work,daemon=True).start();self.stream=sd.InputStream(samplerate=dfx.FS,channels=1,dtype='float32',device=self.inp,blocksize=1200,callback=lambda a,f,t,s:self.q.put(a[:,0].copy()));self.stream.start();self.status.emit('RX started')
    def stop(self):
        self.running=False
        if self.stream:
            try:self.stream.stop();self.stream.close()
            except:pass
            self.stream=None
        self.status.emit('RX stopped')
    def work(self):
        last=0
        while self.running:
            try:a=self.q.get(timeout=.5)
            except queue.Empty:continue
            self.buf.extend(a.tolist());n=2048;z=a[:n] if len(a)>=n else np.pad(a,(0,n-len(a)));self.spec.emit(20*np.log10(np.abs(np.fft.rfft(z*np.hanning(n)))+1e-9))
            if len(self.buf)>=dfx.FS*2:
                try:self.snr.emit(float(dfx.estimate_snr2500(list(self.buf)[-dfx.FS*2:])))
                except:pass
            if time.time()-last>1.5 and len(self.buf)>dfx.FS*3:
                last=time.time();data=list(self.buf);profiles=[p for p in ('FAST','DX','WEAK','DEEP') if len(data)>=dfx.profile_duration(p)*dfx.FS]
                try:
                    for r in self.decoder.decode(data,profiles,5):self.decoded.emit(r)
                except Exception as e:self.status.emit(str(e))
    def tx(self,msg,profile,parity,center):
        delay=dfx.next_tx_delay(profile,parity);self.status.emit(f'TX in {delay:.1f}s')
        def run():
            time.sleep(delay);a=np.asarray(dfx.modulate(msg,profile,center),dtype=np.float32)
            try:self.rig.ptt(True);time.sleep(.08);sd.play(a,dfx.FS,device=self.out,blocking=True);time.sleep(.05)
            finally:self.rig.ptt(False)
            self.status.emit('TX complete')
        threading.Thread(target=run,daemon=True).start()

class Main(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('DFX v0.50');self.resize(1100,760);self.rig=Rig();self.eng=Engine(self.rig);self.ad=dfx.AdaptiveController('DX');self.lastsnr=-20
        w=QtWidgets.QWidget();self.setCentralWidget(w);v=QtWidgets.QVBoxLayout(w);r=QtWidgets.QHBoxLayout();self.ind=QtWidgets.QComboBox();self.outd=QtWidgets.QComboBox()
        for i,d in enumerate(sd.query_devices()):
            if d['max_input_channels']>0:self.ind.addItem(f"{i}: {d['name']}",i)
            if d['max_output_channels']>0:self.outd.addItem(f"{i}: {d['name']}",i)
        self.start=QtWidgets.QPushButton('Start RX');self.stop=QtWidgets.QPushButton('Stop RX');self.snr=QtWidgets.QLabel('S/N --')
        for x in [QtWidgets.QLabel('Input'),self.ind,QtWidgets.QLabel('Output'),self.outd,self.start,self.stop,self.snr]:r.addWidget(x)
        v.addLayout(r);self.wf=Waterfall();v.addWidget(self.wf);self.tbl=QtWidgets.QTableWidget(0,5);self.tbl.setHorizontalHeaderLabels(['UTC','Profile','S/N','Audio Hz','Message']);self.tbl.horizontalHeader().setStretchLastSection(True);v.addWidget(self.tbl,1)
        g=QtWidgets.QGridLayout();self.call=QtWidgets.QLineEdit('MM0DFV');self.grid=QtWidgets.QLineEdit('IO75');self.dx=QtWidgets.QLineEdit();self.rep=QtWidgets.QSpinBox();self.rep.setRange(-50,49);self.rep.setValue(-15);self.prof=QtWidgets.QComboBox();self.prof.addItems(['AUTO','FAST','DX','WEAK','DEEP']);self.par=QtWidgets.QComboBox();self.par.addItems(['Even','Odd']);self.center=QtWidgets.QSpinBox();self.center.setRange(-500,500);self.msg=QtWidgets.QLineEdit('CQ MM0DFV IO75')
        items=[('My Call',self.call),('Grid',self.grid),('DX Call',self.dx),('Report',self.rep),('Profile',self.prof),('TX Slot',self.par),('Audio offset',self.center),('Message',self.msg)]
        for i,(t,x) in enumerate(items):g.addWidget(QtWidgets.QLabel(t),i//2,(i%2)*2);g.addWidget(x,i//2,(i%2)*2+1)
        v.addLayout(g);b=QtWidgets.QHBoxLayout()
        for t,f in [('CQ',self.cq),('Call',self.callmsg),('Report',self.reportmsg),('R-Report',self.rreport),('RR73',self.rr73),('73',self.seventy3),('TX Next Slot',self.tx)]:q=QtWidgets.QPushButton(t);q.clicked.connect(f);b.addWidget(q)
        v.addLayout(b);self.start.clicked.connect(self.rx);self.stop.clicked.connect(self.eng.stop);self.eng.spec.connect(self.wf.add);self.eng.snr.connect(self.snrset);self.eng.decoded.connect(self.decoded);self.eng.status.connect(self.statusBar().showMessage);self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.clock);self.timer.start(250);self.load()
    def profile(self):return self.ad.profile if self.prof.currentText()=='AUTO' else self.prof.currentText()
    def snrset(self,x):self.lastsnr=x;self.ad.update(x,True);self.snr.setText(f'S/N {x:.1f} dB | {self.profile()}')
    def decoded(self,r):
        n=self.tbl.rowCount();self.tbl.insertRow(n);vals=[time.strftime('%H:%M:%S',time.gmtime()),r['profile'],f'{self.lastsnr:.1f}',f"{r.get('freq_offset',0):+.0f}",r['message']]
        for i,x in enumerate(vals):self.tbl.setItem(n,i,QtWidgets.QTableWidgetItem(x))
    def rx(self):self.eng.inp=self.ind.currentData();self.eng.out=self.outd.currentData();self.eng.start()
    def base(self):return self.call.text().strip().upper(),self.grid.text().strip().upper(),self.dx.text().strip().upper()
    def cq(self):a,g,d=self.base();self.msg.setText(f'CQ {a} {g}')
    def callmsg(self):a,g,d=self.base();self.msg.setText(f'{d} {a} {g}') if d else None
    def reportmsg(self):a,g,d=self.base();self.msg.setText(f'{d} {a} {self.rep.value():+d}') if d else None
    def rreport(self):a,g,d=self.base();self.msg.setText(f'{d} {a} R{self.rep.value():+d}') if d else None
    def rr73(self):a,g,d=self.base();self.msg.setText(f'{d} {a} RR73') if d else None
    def seventy3(self):a,g,d=self.base();self.msg.setText(f'{d} {a} 73') if d else None
    def tx(self):p=self.profile();m=self.msg.text().strip().upper();dfx.build_frame(m,p);self.eng.out=self.outd.currentData();self.eng.tx(m,p,self.par.currentIndex(),self.center.value())
    def clock(self):self.statusBar().showMessage(f"UTC {time.strftime('%H:%M:%S',time.gmtime())} | {self.profile()}")
    def load(self):
        if SETTINGS.exists():
            try:d=json.loads(SETTINGS.read_text());self.call.setText(d.get('call','MM0DFV'));self.grid.setText(d.get('grid','IO75'))
            except:pass
    def closeEvent(self,e):SETTINGS.write_text(json.dumps({'call':self.call.text(),'grid':self.grid.text()}));self.eng.stop();self.rig.close();e.accept()

def main():a=QtWidgets.QApplication(sys.argv);w=Main();w.show();sys.exit(a.exec())
if __name__=='__main__':main()
