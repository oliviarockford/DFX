import os,re,subprocess,tempfile,wave,struct,sys
from pathlib import Path

LINE_RE=re.compile(r"^(FAST|DX|WEAK|DEEP)\s+\|\s+([\-0-9.eE]+)\s+Hz\s+\|\s+drift\s+([\-0-9.eE]+)\s+\|\s+score\s+([\-0-9.eE]+)\s+\|\s+sync\s+(\d+)\s+\|\s+(.+)$")

class NativeDecoder:
    def __init__(self,appdir=None):
        frozen_dir=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
        self.appdir=Path(appdir or frozen_dir)
        names=["dfx_decode.exe","dfx_decode","dfx_decode_linux_x86_64"]
        self.exe=next((self.appdir/n for n in names if (self.appdir/n).exists()),None)
    @property
    def available(self):return self.exe is not None
    def _write_wav(self,samples,path,fs=12000):
        vals=[float(v) for v in samples]
        peak=max([1e-9]+[abs(v) for v in vals])
        with wave.open(str(path),"wb") as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(fs)
            f.writeframes(b"".join(struct.pack("<h",int(max(-1,min(1,v/peak))*32767)) for v in vals))
    def decode(self,samples,profiles=("FAST","DX","WEAK","DEEP"),timeout=6):
        if not self.available:return []
        fd,name=tempfile.mkstemp(prefix="dfx_rx_",suffix=".wav")
        os.close(fd);p=Path(name)
        try:
            self._write_wav(samples,p)
            out=[]
            for profile in profiles:
                try:
                    r=subprocess.run([str(self.exe),profile,str(p)],capture_output=True,text=True,timeout=timeout)
                except subprocess.TimeoutExpired:
                    continue
                for line in r.stdout.splitlines():
                    m=LINE_RE.match(line.strip())
                    if not m:continue
                    out.append({"profile":m.group(1),"freq_offset":float(m.group(2)),
                                "drift":float(m.group(3)),"metric":float(m.group(4)),
                                "sync":int(m.group(5)),"message":m.group(6).strip()})
            seen=set();res=[]
            for r in sorted(out,key=lambda x:(x["profile"],x["freq_offset"])):
                k=(r["profile"],r["message"],round(r["freq_offset"],1))
                if k not in seen:seen.add(k);res.append(r)
            return res
        finally:
            try:p.unlink()
            except Exception:pass
