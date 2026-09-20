import json
import tempfile
import unittest
from pathlib import Path
from ascon_app.protocol import *
from ascon_app.transport import DemoTransport, exchange_stream
from ascon_app.service import run_operation, save_result

class FakeStream:
    def __init__(self, response):
        self.response=bytearray(response);self.written=bytearray()
    def reset_input_buffer(self):pass
    def write(self, data):
        n=min(7,len(data));self.written.extend(data[:n]);return n
    def read(self, n):
        chunk=bytes(self.response[:min(3,n)]);del self.response[:len(chunk)];return chunk

class AppTests(unittest.TestCase):
    def request(self, **kwargs):
        args=dict(key=DEFAULT_KEY,nonce=DEFAULT_NONCE,ad=DEFAULT_AD,plaintext=DEFAULT_PLAINTEXT)
        args.update(kwargs);return make_request(**args)
    def test_layout(self):
        packet=encode_request(self.request())
        self.assertEqual(len(packet),68)
        self.assertEqual(packet[:4],bytes([0xa5,1,5,10]))
        self.assertEqual(packet[4:20],bytes(range(16)))
        self.assertEqual(packet[36:52],b'ASCON'+bytes(11))
        self.assertEqual(packet[52:68],b'hello FPGA'+bytes(6))
    def test_defaults_and_empty(self):
        req=make_request('','','','')
        self.assertEqual(req.key,bytes(range(16)))
        self.assertEqual(req.ad,b'ASCON');self.assertEqual(len(req.nonce),16)
        self.assertEqual(self.request(empty_ad=True,empty_pt=True).plaintext,b'')
    def test_utf8_limits(self):
        with self.assertRaises(ValueError):self.request(plaintext='අ'*6)
        with self.assertRaises(ValueError):self.request(ad='a'*17)
    def test_invalid_hex_key_nonce(self):
        for value in ('f','zz','00'):
            with self.assertRaises(ValueError):self.request(key=value)
        with self.assertRaises(ValueError):self.request(nonce='00')
    def test_golden_encryption(self):
        result=run_operation(DemoTransport(),self.request(),'demo')
        self.assertEqual(result['ciphertext_hex'],DEFAULT_CT)
        self.assertEqual(result['tag_hex'],DEFAULT_TAG)
    def test_decryption(self):
        req=self.request(decrypt=True,plaintext=DEFAULT_CT,tag=DEFAULT_TAG)
        self.assertEqual(len(encode_request(req)),84);self.assertEqual(encode_request(req)[1],2)
        result=run_operation(DemoTransport(),req,'demo')
        self.assertEqual(bytes.fromhex(result['plaintext_hex']),b'hello FPGA')
        self.assertEqual(result['authentication'],'verified')
    def test_authentication_failure(self):
        req=self.request(decrypt=True,plaintext=DEFAULT_CT,tag='00'*16)
        raw=DemoTransport().exchange(encode_request(req))
        self.assertEqual(raw,b'\x5a\x03'+bytes(32))
        with self.assertRaisesRegex(ProtocolError,'Authentication failed'):decode_response(raw,10)
    def test_fragmented_serial(self):
        packet=encode_request(self.request());raw=DemoTransport().exchange(packet);stream=FakeStream(raw)
        self.assertEqual(exchange_stream(stream,packet),raw);self.assertEqual(bytes(stream.written),packet)
    def test_timeout(self):
        with self.assertRaises(TimeoutError):exchange_stream(FakeStream(b''),encode_request(self.request()),0.001)
    def test_bad_responses(self):
        for raw in (bytes(34),b'\x5a\x00',b'\x5a\x01'+bytes(32),b'\x5a\x02'+bytes(32),b'\x5a\x7f'+bytes(32)):
            with self.assertRaises(ProtocolError):decode_response(raw,0)
        with self.assertRaises(ProtocolError):decode_response(b'\x5a\x00'+b'X'+bytes(31),0)
    def test_export_excludes_secrets(self):
        result=run_operation(DemoTransport(),self.request(decrypt=True,plaintext=DEFAULT_CT,tag=DEFAULT_TAG),'demo')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'result.json';save_result(path,result);saved=json.loads(path.read_text())
        self.assertNotIn('plaintext_hex',saved);self.assertNotIn('response_hex',saved)
        self.assertNotIn(DEFAULT_KEY,json.dumps(saved));self.assertEqual(saved['ciphertext_hex'],DEFAULT_CT)

if __name__=='__main__':unittest.main()
