from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import dfx_core_v050 as dfx
from native_decoder import NativeDecoder

MSG="CQ MM0DFV IO75"
print("DFX v0.50 self-test")
for p in ("FAST","DX","WEAK","DEEP"):
    print(f"{p:5s} frame {dfx.profile_duration(p):.2f}s")

c=dfx.AdaptiveController("FAST")
for snr in (-25,-25,-30,-30,-36,-36,-33,-33,-27,-27,-22,-22):
    c.update(snr,True)
print("Controller final:",c.profile)
assert c.profile=="FAST"

nd=NativeDecoder(ROOT)
if not nd.available:
    raise SystemExit("Native decoder not found. Build dfx_decode.exe first.")
for p in ("FAST","DX","WEAK","DEEP"):
    rs=nd.decode(dfx.modulate(MSG,p,40),profiles=(p,),timeout=8)
    ok=any(r["message"]==MSG for r in rs)
    print(p,"decode","PASS" if ok else "FAIL")
    assert ok
print("ALL TESTS PASSED")
