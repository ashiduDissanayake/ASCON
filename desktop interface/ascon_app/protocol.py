"""Pure validation and packet functions; no UI or serial dependency."""
from dataclasses import dataclass
import secrets

DEFAULT_KEY = '000102030405060708090a0b0c0d0e0f'
DEFAULT_AD = 'ASCON'
DEFAULT_PLAINTEXT = 'hello FPGA'
DEFAULT_NONCE = '101112131415161718191a1b1c1d1e1f'
DEFAULT_CT = '41526d4d50689585ea2d'
DEFAULT_TAG = '722172428e2b0f85e3a7cd2f7845572e'

class ProtocolError(ValueError):
    pass

@dataclass(frozen=True)
class Request:
    key: bytes
    nonce: bytes
    ad: bytes
    plaintext: bytes  # Input payload: plaintext for encrypt, ciphertext for decrypt
    decrypt: bool = False
    tag: bytes = b''

    def __post_init__(self):
        if len(self.key) != 16 or len(self.nonce) != 16:
            raise ValueError('Key and nonce must each contain exactly 16 bytes (32 hex digits).')
        if self.decrypt and len(self.tag) != 16:
            raise ValueError('Decryption requires a 16-byte authentication tag (32 hex digits).')
        if len(self.ad) > 16 or len(self.plaintext) > 16:
            raise ValueError('This FPGA interface supports at most 16 bytes of AD and 16 bytes of plaintext.')

@dataclass(frozen=True)
class Response:
    ciphertext: bytes
    tag: bytes
    raw: bytes


def new_nonce():
    return secrets.token_hex(16)


def parse_hex(value, label):
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f'{label}: enter an even number of hexadecimal digits; spaces are allowed.') from exc


def make_request(key, nonce, ad, plaintext, mode='UTF-8 text', empty_ad=False, empty_pt=False, decrypt=False, tag=''):
    if mode not in ('UTF-8 text', 'Hex bytes'):
        raise ValueError('Unknown input encoding.')
    key_bytes = parse_hex(key.strip() or DEFAULT_KEY, 'Key')
    nonce_bytes = parse_hex(nonce.strip() or (DEFAULT_NONCE if decrypt else new_nonce()), 'Nonce')
    def payload(value, default, empty, label):
        if empty:
            return b''
        if value == '':
            return default.encode('utf-8')
        return value.encode('utf-8') if mode == 'UTF-8 text' else parse_hex(value, label)
    return Request(key_bytes, nonce_bytes,
                   payload(ad, DEFAULT_AD, empty_ad, 'AD'),
                   (b'' if empty_pt else parse_hex(plaintext.strip() or DEFAULT_CT, 'Ciphertext')) if decrypt else payload(plaintext, DEFAULT_PLAINTEXT, empty_pt, 'Data'), decrypt,
                   parse_hex(tag.strip() or DEFAULT_TAG, 'Tag') if decrypt else b'')


def encode_request(request):
    return (bytes([0xA5, 2 if request.decrypt else 1, len(request.ad), len(request.plaintext)]) +
            request.key + request.nonce + request.ad.ljust(16, b'\0') +
            request.plaintext.ljust(16, b'\0') + (request.tag if request.decrypt else b''))


def decode_response(raw, plaintext_length):
    if not 0 <= plaintext_length <= 16:
        raise ProtocolError('Invalid expected plaintext length.')
    if len(raw) != 34:
        raise ProtocolError(f'Expected 34 response bytes; received {len(raw)}.')
    if raw[0] != 0x5A:
        raise ProtocolError('Wrong response marker. Check FPGA firmware and baud rate.')
    if raw[1] != 0:
        meanings = {1: 'FPGA rejected the command (status 01). For decryption, install the UART v2 ascon_uart_protocol.v, rebuild the bitstream and program the FPGA. Then press btnC and reconnect. Resetting alone does not update the bitstream.', 2: 'FPGA rejected an input length', 3: 'Authentication failed. No plaintext was released.'}
        raise ProtocolError(meanings.get(raw[1], f'Unknown FPGA status 0x{raw[1]:02x}'))
    if any(raw[2+plaintext_length:18]):
        raise ProtocolError('Nonzero ciphertext padding: response does not match the fixed-frame protocol.')
    return Response(raw[2:2+plaintext_length], raw[18:34], raw)
