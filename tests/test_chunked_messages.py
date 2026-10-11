"""End-to-end host framing, serial records, authentication and GUI orchestration."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'desktop interface'))
from ascon_app.messages import MessageDecryptRequest, validate_envelope
from ascon_app.protocol import Request, ProtocolError
from ascon_app.service import run_operation, save_result
from ascon_app.transport import DemoTransport, exchange_stream
from test_bounded_transport import Stream, records, frame

class UARTTransport:
    """Independent reference output through actual host UART framing/parser."""
    def __init__(self, bounded=True, old=False):
        self.calls = []
        self.bounded, self.old = bounded, old
    def run(self, request):
        self.calls.append(request)
        response = DemoTransport().run(request)
        wire = records(request, self.bounded, not self.old)
        output = iter(response.ciphertext[i:i+16] for i in range(0, len(response.ciphertext), 16))
        wire = [frame(r[1], r[2], next(output)) if r[1] in (0x12, 0x14)
                else frame(0x13, 16, response.tag) if r[1] == 0x13 else r for r in wire]
        stream = Stream(wire)
        result = exchange_stream(stream, request)
        assert b''.join(stream.writes[1:]) == request.ad+request.plaintext
        return result

class MessageTests(unittest.TestCase):
    def request(self, length=1000, ad=b'mission metadata'):
        return Request(b'k'*16, b'n'*16, ad, bytes(i%256 for i in range(length)))
    def encrypt(self, request=None, transport=None):
        return run_operation(transport or DemoTransport(), request or self.request(), 'test')
    def decrypt(self, envelope, transport=None):
        return run_operation(transport or DemoTransport(), MessageDecryptRequest(b'k'*16, envelope), 'test')

    def test_boundaries_and_binary_round_trip_on_both_firmwares(self):
        for bounded, old in [(True, False), (True, True), (False, False)]:
            for length in [257, 512, 1000, 8192]:
                with self.subTest(bounded=bounded, old=old, length=length):
                    transport = UARTTransport(bounded, old)
                    request = self.request(length)
                    result = self.encrypt(request, transport)
                    self.assertEqual([len(r.plaintext) for r in transport.calls],
                                     [256]*(length//256)+([length%256] if length%256 else []))
                    self.assertTrue(all(len(r.ad) == 48 for r in transport.calls))
                    self.assertEqual(len({r.nonce for r in transport.calls}), result['chunk_count'])
                    plain = self.decrypt(result['message'], UARTTransport(bounded, old))
                    self.assertEqual(bytes.fromhex(plain['plaintext_hex']), request.plaintext)
                    self.assertEqual(result['total_execution_us'] is not None, bounded)

    def test_small_message_format_unchanged(self):
        for length in [0, 1, 255, 256]:
            result = self.encrypt(self.request(length))
            self.assertEqual(result['format'], 'basys3-ascon-result-v3')
            self.assertNotIn('message', result)
            self.assertEqual(len(result['tag_hex']), 32)

    def test_nonce_freshness_and_progress(self):
        request = self.request()
        progress = []
        first = run_operation(DemoTransport(), request, 'test', lambda n, total: progress.append((n,total)))
        second = self.encrypt(request)
        self.assertNotEqual(first['nonce_hex'], second['nonce_hex'])
        self.assertEqual(progress, [(1,4), (2,4), (3,4), (4,4)])

    def test_framing_errors_are_rejected_before_uart(self):
        envelope = self.encrypt()['message']
        variants = []
        for transform in [lambda e: e['chunks'].pop(),
                          lambda e: e['chunks'].reverse(),
                          lambda e: e['chunks'].__setitem__(1, copy.deepcopy(e['chunks'][0])),
                          lambda e: e['chunks'][0].__setitem__('nonce_hex', '00'*16),
                          lambda e: e.__setitem__('plaintext_bytes', 999),
                          lambda e: e.__setitem__('plaintext_bytes', True),
                          lambda e: e['chunks'][0].__setitem__('tag_hex', 'zz'),
                          lambda e: e.__setitem__('base_nonce_hex', 'ff'*16),
                          lambda e: e.__setitem__('algorithm', 'other')]:
            variant = copy.deepcopy(envelope)
            transform(variant)
            variants.append(variant)
        for variant in variants:
            transport = UARTTransport()
            with self.assertRaises(ProtocolError):
                self.decrypt(variant, transport)
            self.assertEqual(transport.calls, [])

    def test_authenticated_metadata_and_late_failure_release_no_message(self):
        envelope = self.encrypt()['message']
        for field in ['associated_data_hex', 'tag_hex', 'ciphertext_hex']:
            variant = copy.deepcopy(envelope)
            target = variant if field == 'associated_data_hex' else variant['chunks'][-1]
            value = bytearray.fromhex(target[field]); value[0] ^= 1
            target[field] = value.hex()
            with self.assertRaisesRegex(ProtocolError, 'Authentication failed'):
                self.decrypt(variant)
        # Splicing a valid chunk from another encryption also fails framing.
        other = self.encrypt()['message']
        variant = copy.deepcopy(envelope); variant['chunks'][-1] = other['chunks'][-1]
        with self.assertRaises(ProtocolError):
            self.decrypt(variant)

    def test_export_import_without_secret_or_plaintext(self):
        request = self.request()
        result = self.encrypt(request)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'message.json'
            save_result(path, result)
            saved = json.loads(path.read_text())
        self.assertNotIn('key', saved)
        self.assertNotIn('plaintext_hex', saved)
        self.assertEqual(self.decrypt(saved['message'])['plaintext_hex'], request.plaintext.hex())
        recovered = self.decrypt(saved['message'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'decrypted.json'; save_result(path, recovered)
            self.assertNotIn('plaintext_hex', json.loads(path.read_text()))

    def test_valid_looking_truncation_and_identity_change_fail_authentication(self):
        envelope = self.encrypt()['message']
        truncated = copy.deepcopy(envelope)
        truncated['plaintext_bytes'] = 512
        truncated['chunks'] = truncated['chunks'][:2]
        changed = copy.deepcopy(envelope)
        base = b'\x01'*16
        changed['base_nonce_hex'] = base.hex()
        for index, chunk in enumerate(changed['chunks']):
            chunk['nonce_hex'] = (int.from_bytes(base, 'big')+index).to_bytes(16, 'big').hex()
        for variant in [truncated, changed]:
            validate_envelope(variant, b'k'*16)
            with self.assertRaisesRegex(ProtocolError, 'Authentication failed'):
                self.decrypt(variant)

    def test_legacy_large_raw_ciphertext_still_decrypts_on_asc3(self):
        request = self.request()
        response = DemoTransport().run(request)
        decrypt = Request(request.key,request.nonce,request.ad,response.ciphertext,True,response.tag)
        result = run_operation(UARTTransport(bounded=False), decrypt, 'test')
        self.assertEqual(result['plaintext_hex'], request.plaintext.hex())
        with self.assertRaisesRegex(ProtocolError, 'ASC4 supports'):
            run_operation(UARTTransport(), decrypt, 'test')

    def test_application_ad_all_lengths_and_limits(self):
        for ad in [b'', b'a'*48, b'a'*8192]:
            request = self.request(257, ad)
            result = self.encrypt(request)
            self.assertEqual(self.decrypt(result['message'])['plaintext_hex'], request.plaintext.hex())
        with self.assertRaises(ValueError):
            self.request(8193)

    def test_gui_send_and_load_previous_chunked_result(self):
        # Headless test invokes the real GUI handlers; Tk variables/widgets are
        # replaced only at the view boundary.
        from ascon_app.ui import App
        class Variable:
            def __init__(self, value=''): self.value=value
            def get(self): return self.value
            def set(self, value): self.value=value
        app = SimpleNamespace(**{name:Variable(value) for name,value in {
            'operation':'Encrypt', 'key':'6b'*16, 'nonce':'6e'*16, 'ad':'mission',
            'data':'x'*1000, 'encoding':'UTF-8 text', 'auto_nonce':True,
            'empty_ad':False, 'empty_data':False, 'tag':'', 'round_trip':'', 'decrypt_format':'Ciphertext hex',
            'output_status':'', 'status':''}.items()})
        app.transport=DemoTransport(); app.source='test'
        app.events=__import__('queue').Queue()
        app._set_result_status=lambda *args: None
        app._json_mode=lambda: App._json_mode(app)
        app._set_decryption_input=lambda request: App._set_decryption_input(app, request)
        app._show=lambda text: None
        app._work=lambda kind, fn: setattr(app, 'result', fn())
        App._send(app)
        self.assertEqual(app.result['chunk_count'], 4)
        encrypted=app.result
        app._defaults=lambda: None
        app.data_label=SimpleNamespace(configure=lambda **kwargs: None)
        app.send_button=SimpleNamespace(configure=lambda **kwargs: None)
        app._states=lambda: None
        app._set_message_input=lambda envelope: App._set_message_input(app, envelope)
        App._load_decrypt(app)
        App._send(app)
        self.assertEqual(app.result['plaintext_hex'], (b'x'*1000).hex())
        self.assertEqual(app.result['message'], encrypted['message'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'message.json'
            save_result(path, encrypted)
            with patch('ascon_app.ui.filedialog.askopenfilename', return_value=str(path)):
                App._import_message(app)
            App._send(app)
            self.assertEqual(app.result['plaintext_hex'], (b'x'*1000).hex())

if __name__ == '__main__':
    unittest.main()
