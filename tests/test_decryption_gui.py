"""GUI state/clipboard/import/verification tests without requiring a display."""
import json
from pathlib import Path
import queue
import sys
import tempfile
from types import SimpleNamespace, MethodType
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'desktop interface'))
from ascon_app.ui import App
from ascon_app.protocol import DEFAULT_KEY, Request, ProtocolError
from ascon_app.messages import MessageDecryptRequest, parse_decryption_json
from ascon_app.transport import DemoTransport
from ascon_app.service import run_operation, save_result

class Variable:
    def __init__(self, value=''):
        self.value, self.traces = value, []
    def get(self): return self.value
    def set(self, value):
        self.value = value
        for callback in self.traces: callback()
    def trace_add(self, kind, callback): self.traces.append(callback)

class Widget:
    def __init__(self): self.config={'state':'normal'}; self.text=''; self.modified=False
    def configure(self, **kwargs): self.config.update(kwargs)
    def cget(self, name): return self.config[name]
    def get(self, *args): return self.text
    def delete(self, *args): self.text=''
    def insert(self, index, text): self.text=text
    def edit_modified(self, value=None):
        if value is not None: self.modified=value
        return self.modified


def view():
    app=SimpleNamespace(**{name:Variable(value) for name,value in {
        'operation':'Encrypt', 'encoding':'UTF-8 text', 'decrypt_format':'Ciphertext hex',
        'key':DEFAULT_KEY, 'nonce':'', 'ad':'', 'data':'', 'tag':'',
        'auto_nonce':True, 'empty_ad':False, 'empty_data':False,
        'status':'', 'output_status':'', 'round_trip':'', 'auth_status':'', 'input_hint':''}.items()})
    names=['data_input','backend_combo','port_combo','decrypt_format_combo','tag_entry','nonce_check',
           'nonce_entry','ad_entry','empty_ad_check','empty_data_check','load_ad_button','load_data_button',
           'encoding_combo','data_label','copy_button','send_button','save_button','decrypt_result_button',
           'connect_button','auth_badge','key_entry']
    for name in names: setattr(app,name,Widget())
    app.controls=[(getattr(app,name), 'readonly' if name.endswith('_combo') else 'normal') for name in names]
    app.pending=False; app.result=None; app.transport=DemoTransport(); app.source='SOFTWARE DEMO'
    app.events=queue.Queue(); app.after=lambda *args: None
    app._show=lambda text: setattr(app,'shown_text',text)
    app.clipboard_clear=lambda: setattr(app,'clipboard','')
    app.clipboard_append=lambda text: setattr(app,'clipboard',text)
    for name in ['_json_mode','_states','_defaults','_set_result_status','_set_message_input',
                 '_set_decryption_input','_sync_data_input','_data_modified','_send','_poll',
                 '_load_decrypt','_copy','_import_message']:
        setattr(app,name,MethodType(getattr(App,name),app))
    app.data.trace_add('write',app._sync_data_input)
    def work(kind, function):
        app.pending=True; app._states()
        try: app.events.put((kind,function(),None))
        except Exception as exc: app.events.put((kind,None,str(exc)))
    app._work=work
    app._defaults()
    return app


def finish(app):
    while not app.events.empty(): app._poll()

class DecryptionGUITests(unittest.TestCase):
    def encrypt(self, length=1000):
        app=view(); app.data.set('x'*length); app._send(); finish(app)
        return app

    def test_copy_chunked_json_paste_full_export_and_verify(self):
        app=self.encrypt()
        self.assertIn('CHUNK 4',app.shown_text)
        self.assertIn(app.result['message']['chunks'][0]['tag_hex'],app.shown_text)
        self.assertEqual(app.copy_button.config['text'],'Copy message JSON')
        encrypted=app.result
        app._copy()
        envelope=json.loads(app.clipboard)
        self.assertEqual(envelope,encrypted['message'])
        self.assertNotIn('key',envelope)
        self.assertNotIn('plaintext_hex',envelope)
        receiver=view(); receiver.operation.set('Decrypt + verify'); receiver._defaults()
        receiver.data.set(json.dumps(encrypted,indent=2))
        self.assertTrue(receiver._json_mode())
        receiver._send(); finish(receiver)
        self.assertEqual(receiver.result['plaintext_hex'],(b'x'*1000).hex())
        receiver._copy()
        self.assertEqual(receiver.clipboard,(b'x'*1000).hex())
        self.assertEqual(receiver.copy_button.config['text'],'Copy output hex')

    def test_metadata_disabled_in_json_mode_and_controls_recover(self):
        app=self.encrypt(); app._load_decrypt()
        self.assertIsNone(app.result)
        self.assertEqual(app.auth_status.get(),'Ready to verify')
        for name in ['nonce_entry','ad_entry','tag_entry','encoding_combo','empty_ad_check',
                     'empty_data_check','load_ad_button','load_data_button','nonce_check']:
            self.assertEqual(getattr(app,name).config['state'],'disabled',name)
        self.assertEqual(app.key_entry.config['state'],'normal')
        self.assertEqual(app.data_input.config['state'],'normal')
        app.pending=True; app._states()
        self.assertEqual(app.data_input.config['state'],'disabled')
        self.assertEqual(app.key_entry.config['state'],'disabled')
        app.pending=False; app._defaults()
        self.assertEqual(app.decrypt_format.get(),'Ciphertext hex')
        self.assertEqual(app.tag_entry.config['state'],'normal')
        self.assertEqual(app.ad_entry.config['state'],'normal')
        self.assertEqual(app.encoding_combo.config['state'],'readonly')
        app.operation.set('Encrypt'); app._defaults()
        self.assertEqual(app.decrypt_format_combo.config['state'],'disabled')
        self.assertEqual(app.nonce_check.config['state'],'normal')

    def test_import_chunked_and_legacy_files_preserves_key_and_empty_flags(self):
        for length in [1,1000]:
            app=self.encrypt(length)
            exported=app.result
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'encrypted.json'; save_result(path,exported)
                with patch('ascon_app.ui.filedialog.askopenfilename',return_value=str(path)):
                    app._import_message()
            self.assertEqual(app.key.get(),DEFAULT_KEY)
            self.assertIsNone(app.result)
            app._send(); finish(app)
            self.assertEqual(app.result['plaintext_hex'],(b'x'*length).hex())
        request=Request(bytes.fromhex(DEFAULT_KEY),b'n'*16,b'',b'')
        exported=run_operation(DemoTransport(),request,'demo')
        parsed=parse_decryption_json(json.dumps(exported),request.key)
        app=view(); app._set_decryption_input(parsed)
        self.assertTrue(app.empty_ad.get()); self.assertTrue(app.empty_data.get())
        app._send(); finish(app)
        self.assertEqual(app.result['plaintext_hex'],'')

    def test_late_authentication_failure_never_displays_plaintext(self):
        app=self.encrypt(); envelope=json.loads(json.dumps(app.result['message']))
        envelope['chunks'][-1]['tag_hex']='00'*16
        app._set_message_input(envelope); app._send(); finish(app)
        self.assertIsNone(app.result)
        self.assertEqual(app.auth_status.get(),'Authentication failed')
        self.assertNotIn('PLAINTEXT',app.shown_text)
        self.assertEqual(app.copy_button.config['state'],'disabled')
        self.assertEqual(app.save_button.config['state'],'disabled')

    def test_multiline_input_preserves_bytes_and_paste_selects_json(self):
        app=view(); app.data.set('line 1\nline 2\n')
        self.assertEqual(app.data_input.text,'line 1\nline 2\n')
        app.data_input.text='edited\ntext'; app.data_input.modified=True; app._data_modified()
        self.assertEqual(app.data.get(),'edited\ntext')
        app.operation.set('Decrypt + verify'); app._defaults()
        app.data_input.text='{\n"format": "test"\n}'; app.data_input.modified=True; app._data_modified()
        self.assertTrue(app._json_mode())

    def test_invalid_json_does_not_close_connection_or_submit(self):
        app=view(); transport=app.transport
        app.operation.set('Decrypt + verify'); app._defaults()
        app.decrypt_format.set('Message / result JSON'); app.data.set('{broken')
        with patch('ascon_app.ui.messagebox.showerror') as showerror:
            app._send()
        showerror.assert_called_once()
        self.assertIs(app.transport,transport)
        self.assertTrue(app.events.empty())

    def test_json_parser_rejects_missing_or_invalid_legacy_fields(self):
        request=Request(b'k'*16,b'n'*16,b'',b'p')
        result=run_operation(DemoTransport(),request,'demo')
        for field in ['nonce_hex','tag_hex','associated_data_hex','ciphertext_hex']:
            malformed=dict(result); del malformed[field]
            with self.assertRaises(ProtocolError): parse_decryption_json(json.dumps(malformed),request.key)
        for value in ['[]','{}','{bad','x'*1_000_001]:
            with self.assertRaises(ProtocolError): parse_decryption_json(value,request.key)

if __name__ == '__main__': unittest.main()
