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
        if len(self.ad) > 0xFFFFFFFF or len(self.plaintext) > 0xFFFFFFFF:
            raise ValueError('UART v3 uses unsigned 32-bit BYTE lengths (maximum 2^32-1 each).')

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
    """Encode only the fixed 58-byte header. Payload follows on FPGA grants."""
    return (bytes([0xA5, 0x12 if request.decrypt else 0x11]) +
            len(request.ad).to_bytes(4, 'little') +
            len(request.plaintext).to_bytes(4, 'little') + request.key +
            request.nonce + (request.tag if request.decrypt else bytes(16)))


def decode_record(raw):
    if len(raw) != 19 or raw[0] != 0x5A:
        raise ProtocolError('Invalid UART v3 record. Install the matching streaming bitstream, press btnC and reconnect.')
    kind, count, payload = raw[1], raw[2], raw[3:]
    if kind == 0x7F:
        errors = {
            1: 'FPGA rejected the command. Program the UART v3 streaming bitstream.',
            3: 'Authentication failed. Provisional plaintext discarded; no result accepted.',
        }
        raise ProtocolError(errors.get(count, f'FPGA error {count:02x}'))
    return kind, count, payload
