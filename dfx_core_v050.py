# dfx_v012.py
import math, random, wave, struct

FS=12000
BASE_FREQ=900.0
AMP=0.72
REF_BW=2500.0
SYNC=[0,7,1,6,2,5,3,4,7,2,6,0,5,1,4,3,0,6,2,7,1,5,3,4]
PILOT=[0,3,7,4,1,6,2,5]
CALL_CHARS=" 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ/"
CALL_BASE=len(CALL_CHARS)
TYPE_CQ=0; TYPE_CALL=1; TYPE_REPORT=2; TYPE_RREPORT=3; TYPE_RR73=4; TYPE_73=5
PROFILES={
    "FAST":{"id":0,"baud":40.0,"spacing":40.0,"mode_bw":320.0,"repeat":1},
    "DX":{"id":1,"baud":25.0,"spacing":25.0,"mode_bw":200.0,"repeat":2},
    "WEAK":{"id":2,"baud":12.5,"spacing":12.5,"mode_bw":100.0,"repeat":0},
    "DEEP":{"id":3,"baud":12.5,"spacing":12.5,"mode_bw":100.0,"repeat":3},
}
G0=0o171; G1=0o133; K=7; TAIL=6; NSTATES=64
INFO=96; RAW=112; BASECODE=236
QC_Z=14;QC_A=[[12, 6, -1, -1, -1, 13, -1, 2], [9, -1, -1, 3, 6, -1, 2, -1], [8, -1, 0, -1, -1, -1, 8, 0], [-1, -1, 9, 7, -1, 0, -1, 0], [-1, 4, 8, -1, 2, 10, -1, -1], [2, -1, 6, -1, 11, -1, -1, 5], [13, -1, 9, 2, -1, 5, -1, -1], [1, 8, -1, 11, -1, -1, -1, 8], [-1, 3, -1, 0, -1, -1, 10, 9], [-1, 4, 4, -1, 7, -1, 11, -1], [1, 3, -1, -1, 8, -1, 7, -1], [-1, -1, -1, -1, 2, 6, 0, 8], [-1, 1, -1, 8, -1, -1, 13, 2], [-1, -1, 8, -1, -1, 6, 13, 0], [-1, 5, -1, 7, 13, -1, 8, -1], [-1, -1, 10, 12, 9, 4, -1, -1]]
def qcenc(raw):
 s=[[0]*14 for _ in range(16)]
 for r in range(16):
  for c in range(8):
   sh=QC_A[r][c]
   if sh<0:continue
   for i in range(14):s[r][i]^=raw[c*14+((i+sh)%14)]
 p=[[0]*14 for _ in range(16)]
 for r in range(16):
  for i in range(14):p[r][i]=s[r][i]^(p[r-1][i] if r else 0)
 out=list(raw)
 for r in range(16):out.extend(p[r])
 return out

def parity(x): return x.bit_count()&1
def crc16(data,init=0xFFFF):
    c=init
    for b in data:
        c^=b<<8
        for _ in range(8): c=((c<<1)^0x1021)&0xFFFF if c&0x8000 else (c<<1)&0xFFFF
    return c
def i2b(v,n): return [(v>>i)&1 for i in range(n-1,-1,-1)]
def b2i(bits):
    v=0
    for b in bits:v=(v<<1)|b
    return v
def b2bytes(bits):
    bits=bits+[0]*((-len(bits))%8);out=bytearray()
    for i in range(0,len(bits),8):out.append(b2i(bits[i:i+8]))
    return bytes(out)
def enc_call(c):
    s=c.upper().strip()
    if len(s)>6: raise ValueError("call max 6")
    s=s.rjust(6);v=0
    for ch in s:v=v*CALL_BASE+CALL_CHARS.index(ch)
    return v
def dec_call(v):
    a=[]
    for _ in range(6):a.append(CALL_CHARS[v%CALL_BASE]);v//=CALL_BASE
    return "".join(reversed(a)).strip()
def enc_grid(g):
    a=ord(g[0])-65;b=ord(g[1])-65;c=int(g[2]);d=int(g[3]);return (((a*18)+b)*10+c)*10+d
def dec_grid(v):
    d=v%10;v//=10;c=v%10;v//=10;b=v%18;v//=18;a=v%18;return f"{chr(65+a)}{chr(65+b)}{c}{d}"
def pack(msg):
    p=msg.upper().split();c1=c2=aux=0
    if p[0]=="CQ":t=TYPE_CQ;c1=enc_call(p[1]);aux=enc_grid(p[2])
    elif p[2]=="RR73":t=TYPE_RR73;c1=enc_call(p[0]);c2=enc_call(p[1])
    elif p[2]=="73":t=TYPE_73;c1=enc_call(p[0]);c2=enc_call(p[1])
    elif p[2].startswith("R"):t=TYPE_RREPORT;c1=enc_call(p[0]);c2=enc_call(p[1]);aux=int(p[2][1:])+50
    elif p[2][0] in "+-" or p[2].isdigit():t=TYPE_REPORT;c1=enc_call(p[0]);c2=enc_call(p[1]);aux=int(p[2])+50
    else:t=TYPE_CALL;c1=enc_call(p[0]);c2=enc_call(p[1]);aux=enc_grid(p[2])
    return i2b(t,3)+i2b(c1,32)+i2b(c2,32)+i2b(aux,16)+[0]*13
def unpack(bits):
    t=b2i(bits[:3]);c1=dec_call(b2i(bits[3:35]));c2=dec_call(b2i(bits[35:67]));a=b2i(bits[67:83])
    if t==TYPE_CQ:return f"CQ {c1} {dec_grid(a)}"
    if t==TYPE_CALL:return f"{c1} {c2} {dec_grid(a)}"
    if t==TYPE_REPORT:return f"{c1} {c2} {a-50:+d}"
    if t==TYPE_RREPORT:return f"{c1} {c2} R{a-50:+d}"
    if t==TYPE_RR73:return f"{c1} {c2} RR73"
    if t==TYPE_73:return f"{c1} {c2} 73"
    raise ValueError
NEXT=[[0,0] for _ in range(64)];OUT=[[None,None] for _ in range(64)]
for s in range(64):
    for b in (0,1):
        r=((s<<1)|b)&127;NEXT[s][b]=r&63;OUT[s][b]=(parity(r&G0),parity(r&G1))
def conv(bits):
    st=0;o=[]
    for b in bits+[0]*TAIL:r=((st<<1)|b)&127;o += [parity(r&G0),parity(r&G1)];st=r&63
    return o
def vit(L):
    steps=len(L)//2;INF=1e50;m=[INF]*64;m[0]=0;ps=[[0]*64 for _ in range(steps)];pb=[[0]*64 for _ in range(steps)]
    for t in range(steps):
        l0,l1=L[2*t],L[2*t+1];nm=[INF]*64
        for s in range(64):
            if m[s]>=INF/2:continue
            for b in (0,1):
                ns=NEXT[s][b];o0,o1=OUT[s][b];c=(max(0,-l0) if o0==0 else max(0,l0))+(max(0,-l1) if o1==0 else max(0,l1));z=m[s]+c
                if z<nm[ns]:nm[ns]=z;ps[t][ns]=s;pb[t][ns]=b
        m=nm
    st=0;d=[0]*steps
    for t in range(steps-1,-1,-1):d[t]=pb[t][st];st=ps[t][st]
    return d[:-TAIL]
def make_header(pid):
    o=[]
    for b in i2b(pid,2):o += [b]*8
    return o
def payload_symbols(msg,profile):
 p=PROFILES[profile];info=pack(msg);raw=info+i2b(crc16(b2bytes(info)),16)
 if profile=="WEAK":rep=qcenc(raw)
 else:
  coded=conv(raw);rep=[]
  for b in coded:rep += [b]*p["repeat"]
 bits=make_header(p["id"])+rep;bits += [0]*((-len(bits))%3)
 return [(bits[i]<<2)|(bits[i+1]<<1)|bits[i+2] for i in range(0,len(bits),3)]
def frame(msg,profile):
    data=payload_symbols(msg,profile);a=len(data)//2;return SYNC + data[:a] + PILOT + data[a:] + PILOT
def frame_layout(msg,profile):
    data=payload_symbols(msg,profile);a=len(data)//2
    return {"sync_start":0,"sync_len":len(SYNC),"pilot1_start":len(SYNC)+a,"pilot2_start":len(SYNC)+a+len(PILOT)+(len(data)-a),"pilot_len":len(PILOT),"total_symbols":len(SYNC)+len(data)+2*len(PILOT),"data_symbols":len(data)}
def mod(msg,profile,center=0.0,drift=0.0,amp=1.0):
    p=PROFILES[profile];sps=int(FS/p["baud"]);ph=0;n=0;o=[]
    for sym in frame(msg,profile):
        for _ in range(sps):
            t=n/FS;f=BASE_FREQ+sym*p["spacing"]+center+drift*t;ph+=2*math.pi*f/FS
            if ph>2*math.pi:ph-=2*math.pi
            o.append(AMP*amp*math.sin(ph));n+=1
    return o
def gp(block,f):
    w=2*math.pi*f/FS;c=2*math.cos(w);q0=q1=q2=0
    for x in block:q0=c*q1-q2+x;q2=q1;q1=q0
    return max(0,q1*q1+q2*q2-c*q1*q2)
def symbol_powers(x,profile,center,drift,timing=0):
    p=PROFILES[profile];sps=int(FS/p["baud"]);sy=[];pw=[];pos=timing
    while pos+sps<=len(x):
        b=x[pos:pos+sps];t=(pos+sps/2)/FS;a=[gp(b,BASE_FREQ+s*p["spacing"]+center+drift*t) for s in range(8)];sy.append(max(range(8),key=lambda k:a[k]));pw.append(a);pos+=sps
    return sy,pw
def match_at(sy,pat,start):
    if start<0 or start+len(pat)>len(sy):return -1
    return sum(a==b for a,b in zip(sy[start:start+len(pat)],pat))
def add_awgn(x,snr2500,profile):
    p=PROFILES[profile];snr_mode=snr2500+10*math.log10(REF_BW/p["mode_bw"]);sp=sum(v*v for v in x)/len(x);np=sp/(10**(snr_mode/10));sg=math.sqrt(np);return [v+random.gauss(0,sg) for v in x]
def mix(xs):
    n=max(map(len,xs));o=[0.0]*n
    for x in xs:
        for i,v in enumerate(x):o[i]+=v
    pk=max(1,max(abs(v) for v in o));return [v/pk for v in o]
def duration(profile):return len(frame("CQ MM0DFV IO75",profile))/PROFILES[profile]["baud"]
for _p,_slot in {"FAST":5.0,"DX":10.0,"WEAK":15.0,"DEEP":30.0}.items():PROFILES[_p]["slot_period"]=_slot
build_frame=frame
profile_duration=duration
def modulate(message,profile,center_offset=0.0):return mod(message,profile,center=center_offset,drift=0.0)
def estimate_snr2500(samples, center_offset=0.0, profile="DX"):
    if samples is None or len(samples)==0:return -50.0
    p=PROFILES[profile];sig_freqs=[BASE_FREQ+s*p["spacing"]+center_offset for s in range(8)];noise_freqs=[1500,1700,1900,2100,2300];sig=max(gp(samples,f) for f in sig_freqs);noise=sum(gp(samples,f) for f in noise_freqs)/len(noise_freqs)
    if noise<=0 or sig<=noise:return -40.0
    snr_mode=10*math.log10((sig-noise)/noise);return snr_mode-10*math.log10(REF_BW/p["mode_bw"])
def utc_slot_state(profile,now=None):
    import time as _time
    if now is None:now=_time.time()
    period=PROFILES[profile]["slot_period"];phase=now%period;return {"period":period,"phase":phase,"seconds_to_boundary":period-phase}
def next_tx_delay(profile,parity=0,now=None):
    import time as _time
    if now is None:now=_time.time()
    period=PROFILES[profile]["slot_period"];idx=int(now//period);target=idx+1
    if target%2!=parity:target+=1
    return max(0.0,target*period-now)
class AdaptiveController:
    ORDER=("FAST","DX","WEAK","DEEP");DOWN={"FAST":-24.2,"DX":-29.4,"WEAK":-35.8};UP={"DX":-22.2,"WEAK":-27.4,"DEEP":-33.8}
    def __init__(self,profile="DX",required=2):self.profile=profile;self.required=required;self.poor_count=0;self.good_count=0;self.fail_count=0
    def reset(self,profile="DX"):self.profile=profile;self.poor_count=self.good_count=self.fail_count=0
    def update(self,snr_db=None,decoded=True):
        if decoded:self.fail_count=0
        else:self.fail_count+=1
        if snr_db is None:
            if self.fail_count>=self.required:self._down();self.fail_count=0
            return self.profile
        p=self.profile
        if p!="DEEP" and (not decoded or snr_db<=self.DOWN[p]):self.poor_count+=1
        else:self.poor_count=0
        if p!="FAST" and decoded and snr_db>=self.UP[p]:self.good_count+=1
        else:self.good_count=0
        if self.fail_count>=self.required or self.poor_count>=self.required:self._down();self.fail_count=self.poor_count=self.good_count=0
        elif self.good_count>=self.required:self._up();self.fail_count=self.poor_count=self.good_count=0
        return self.profile
    def _down(self):
        i=self.ORDER.index(self.profile)
        if i<len(self.ORDER)-1:self.profile=self.ORDER[i+1]
    def _up(self):
        i=self.ORDER.index(self.profile)
        if i>0:self.profile=self.ORDER[i-1]
class QSOStateMachine:
    def __init__(self,mycall,grid):self.mycall=mycall.upper();self.grid=grid.upper();self.dxcall="";self.state="IDLE";self.last_report=-15
    def reset(self):self.dxcall="";self.state="IDLE"
    def set_identity(self,mycall,grid):self.mycall=mycall.upper();self.grid=grid.upper()
    def start_cq(self):self.state="CQ";return f"CQ {self.mycall} {self.grid}"
    def process_rx(self,message,report=-15):
        if not message:return None
        p=message.upper().split()
        if len(p)<3:return None
        self.last_report=int(round(report))
        if p[0]=="CQ":self.dxcall=p[1];self.state="CALLING";return f"{self.dxcall} {self.mycall} {self.grid}"
        if p[0]!=self.mycall:return None
        sender=p[1]
        if not self.dxcall:self.dxcall=sender
        if sender!=self.dxcall:return None
        payload=p[2]
        if payload=="RR73":self.state="COMPLETE";return f"{self.dxcall} {self.mycall} 73"
        if payload=="73":self.state="COMPLETE";return None
        if len(payload)==4 and 'A'<=payload[0]<='R' and 'A'<=payload[1]<='R' and payload[2:].isdigit():self.state="REPORT";return f"{self.dxcall} {self.mycall} {self.last_report:+d}"
        if payload.startswith("-") or payload.startswith("+") or payload.isdigit():self.state="RREPORT";return f"{self.dxcall} {self.mycall} R{self.last_report:+d}"
        if payload.startswith("R"):self.state="RR73";return f"{self.dxcall} {self.mycall} RR73"
        return None
