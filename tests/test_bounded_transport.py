import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop interface'))
from ascon_app.protocol import Request,ProtocolError
from ascon_app.transport import exchange_stream
from ascon_app.service import run_operation

def frame(kind,count,payload=b''):
    return bytes([0x5a,kind,count])+payload.ljust(16,b'\0')

class Stream:
    def __init__(self,records):self.data=bytearray(b''.join(records));self.writes=[]
    def reset_input_buffer(self):pass
    def read(self,count):
        # Exercise partial record reads too.
        count=min(count,7);part=bytes(self.data[:count]);del self.data[:count];return part
    def write(self,data):self.writes.append(bytes(data));return len(data)

def records(request,bounded=True,variable_ad=True):
    hello=(b'ASC4'+(256).to_bytes(4,'little')+b'\0'+(48).to_bytes(4,'little')+bytes([variable_ad])+b'\0'*2
           if bounded else b'ASC3'+(8192).to_bytes(4,'little')+b'\1'+b'\0'*7)
    result=[frame(1,4 if bounded else 3,hello)]
    for kind,data in [(0x10,request.ad),(0x11,request.plaintext)]:
        for offset in range(0,len(data),16):result.append(frame(kind,min(16,len(data)-offset)))
    if bounded:
        cycles=27+8*((len(request.ad)//16+1) if request.ad else 0)+8*(len(request.plaintext)//16)
        result.append(frame(0x15,8,cycles.to_bytes(4,'little')+(100_000_000).to_bytes(4,'little')))
    for offset in range(0,len(request.plaintext),16):
        chunk=request.plaintext[offset:offset+16]
        result.append(frame(0x14 if request.decrypt else 0x12,len(chunk),chunk))
    result.append(frame(0x13,16,request.tag if request.decrypt else b't'*16))
    return result

class TransportTests(unittest.TestCase):
    def request(self,m=16,decrypt=False):
        return Request(b'k'*16,b'n'*16,b'a'*48,bytes(range(256))[:m],decrypt,b't'*16 if decrypt else b'')
    def test_bounded_lengths_directions_and_timing(self):
        for m in [1,15,16,17,128,255,256]:
            for dec in [False,True]:
                with self.subTest(length=m,decrypt=dec):
                    request=self.request(m,dec);stream=Stream(records(request))
                    response=exchange_stream(stream,request)
                    self.assertEqual(response.ciphertext,request.plaintext)
                    self.assertEqual(response.execution_cycles,59+8*(m//16))
                    self.assertEqual(b''.join(stream.writes[1:]),request.ad+request.plaintext)
    def test_legacy_has_no_execution_timing(self):
        request=self.request();response=exchange_stream(Stream(records(request,False)),request)
        self.assertIsNone(response.execution_cycles)
    def test_every_ad_length_including_empty(self):
        for a in range(49):
            for dec in [False,True]:
                with self.subTest(ad=a,decrypt=dec):
                    request=Request(b'k'*16,b'n'*16,b'a'*a,b'p'*17,dec,b't'*16 if dec else b'')
                    stream=Stream(records(request))
                    response=exchange_stream(stream,request)
                    self.assertEqual(response.ciphertext,request.plaintext)
                    self.assertEqual(b''.join(stream.writes[1:]),request.ad+request.plaintext)
    def test_old_asc4_still_works_and_rejects_variable_ad(self):
        request=self.request()
        self.assertEqual(exchange_stream(Stream(records(request,variable_ad=False)),request).execution_cycles,67)
        request=Request(b'k'*16,b'n'*16,b'',b'p')
        with self.assertRaisesRegex(ProtocolError,'older ASC4'):
            exchange_stream(Stream(records(request,variable_ad=False)),request)
    def test_invalid_asc4_lengths(self):
        for a,m in [(49,1),(0,0),(48,257)]:
            request=Request(b'k'*16,b'n'*16,b'a'*a,b'p'*m)
            with self.assertRaises(ProtocolError):
                exchange_stream(Stream(records(request)),request)
    def test_missing_duplicate_wrong_and_premature_timing_rejected(self):
        request=self.request();base=records(request);index=next(i for i,r in enumerate(base) if r[1]==0x15)
        variants=[base[:index]+base[index+1:],base[:index]+[base[index]]+base[index:],
                  base[:index]+[frame(0x15,8,(200).to_bytes(4,'little')+(100_000_000).to_bytes(4,'little'))]+base[index+1:],
                  [base[0],base[index]]+base[1:index]+base[index+1:]]
        for variant in variants:
            with self.assertRaises(ProtocolError):exchange_stream(Stream(variant),request)
    def test_authentication_failure_returns_no_response(self):
        request=self.request(decrypt=True);base=records(request);index=next(i for i,r in enumerate(base) if r[1]==0x15)
        with self.assertRaisesRegex(ProtocolError,'Authentication failed'):
            exchange_stream(Stream(base[:index]+[frame(0x7f,3)]),request)
    def test_service_keeps_hardware_and_host_times_separate(self):
        request=self.request(256)
        class Transport:
            def run(self,r):return exchange_stream(Stream(records(r)),r)
        result=run_operation(Transport(),request,'test')
        self.assertEqual(result['execution_cycles'],187)
        self.assertAlmostEqual(result['execution_us'],1.87)
        self.assertIn('round_trip_ms',result)

if __name__=='__main__':unittest.main()
