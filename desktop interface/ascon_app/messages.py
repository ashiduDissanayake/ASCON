"""Versioned host message framing above the unchanged single-operation UART ABI."""
from dataclasses import dataclass
import hashlib
import secrets
import struct
from .protocol import Request, ProtocolError

FORMAT = 'basys3-ascon-message-v1'
MAX_MESSAGE_BYTES = 8192
CHUNK_BYTES = 256

@dataclass(frozen=True)
class MessageDecryptRequest:
    key: bytes
    envelope: dict
    decrypt: bool = True

    def __post_init__(self):
        if len(self.key) != 16:
            raise ValueError('Key must contain exactly 16 bytes.')


def chunk_ad(ad, base_nonce, index, count, length):
    # Full SHA-256 binds the application AD and message identity. The 16-byte
    # suffix authenticates framing, ordering and length; total AD is 48 bytes.
    digest = hashlib.sha256(b'ASCON-message-v1\0' + len(ad).to_bytes(4, 'little') + ad + base_nonce).digest()
    return digest + struct.pack('<4sIII', b'AMC1', index, count, length)


def chunk_nonce(base_nonce, index):
    return (int.from_bytes(base_nonce, 'big') + index).to_bytes(16, 'big')


def encrypt_message(transport, request, progress=None):
    length = len(request.plaintext)
    if not 256 < length <= MAX_MESSAGE_BYTES:
        raise ValueError('Chunked messages require 257–8192 payload bytes.')
    count = (length + CHUNK_BYTES - 1) // CHUNK_BYTES
    # Fresh 128-bit random range per message, independent of the GUI nonce.
    # No persistent counter to reset/reuse after an application restart.
    base = secrets.randbelow((1 << 128) - count + 1).to_bytes(16, 'big')
    envelope = {'format': FORMAT, 'algorithm': 'Ascon-AEAD128',
                'base_nonce_hex': base.hex(), 'associated_data_hex': request.ad.hex(),
                'plaintext_bytes': length, 'chunks': []}
    responses = []
    for index in range(count):
        payload = request.plaintext[index*CHUNK_BYTES:(index+1)*CHUNK_BYTES]
        nonce = chunk_nonce(base, index)
        response = transport.run(Request(request.key, nonce, chunk_ad(request.ad, base, index, count, length), payload))
        if len(response.ciphertext) != len(payload) or len(response.tag) != 16:
            raise ProtocolError('Malformed chunk encryption response.')
        envelope['chunks'].append({'index': index, 'nonce_hex': nonce.hex(),
                                   'ciphertext_hex': response.ciphertext.hex(), 'tag_hex': response.tag.hex()})
        responses.append(response)
        if progress:
            progress(index+1, count)
    return envelope, responses


def validate_envelope(envelope, key):
    """Validate all structure before submitting any operation to the FPGA."""
    def fail():
        raise ProtocolError('Invalid chunked message: malformed, missing, duplicate or reordered chunks.')
    def hex_bytes(value, size=None):
        if not isinstance(value, str) or len(value) > MAX_MESSAGE_BYTES*2:
            fail()
        try:
            result = bytes.fromhex(value)
        except ValueError:
            fail()
        if size is not None and len(result) != size:
            fail()
        return result
    if not isinstance(envelope, dict) or envelope.get('format') != FORMAT or envelope.get('algorithm') != 'Ascon-AEAD128':
        fail()
    length = envelope.get('plaintext_bytes')
    if type(length) is not int or not 256 < length <= MAX_MESSAGE_BYTES:
        fail()
    base = hex_bytes(envelope.get('base_nonce_hex'), 16)
    ad = hex_bytes(envelope.get('associated_data_hex'))
    count = (length+CHUNK_BYTES-1)//CHUNK_BYTES
    chunks = envelope.get('chunks')
    if not isinstance(chunks, list) or len(chunks) != count or int.from_bytes(base, 'big')+count-1 >= 1 << 128:
        fail()
    requests = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict) or type(chunk.get('index')) is not int or chunk['index'] != index:
            fail()
        nonce = hex_bytes(chunk.get('nonce_hex'), 16)
        if nonce != chunk_nonce(base, index):
            fail()
        payload = hex_bytes(chunk.get('ciphertext_hex'), min(CHUNK_BYTES, length-index*CHUNK_BYTES))
        tag = hex_bytes(chunk.get('tag_hex'), 16)
        requests.append(Request(key, nonce, chunk_ad(ad, base, index, count, length), payload, True, tag))
    return requests


def decrypt_message(transport, request, progress=None):
    requests = validate_envelope(request.envelope, request.key)
    plaintext = bytearray()
    responses = []
    try:
        for index, chunk in enumerate(requests):
            response = transport.run(chunk)
            if len(response.ciphertext) != len(chunk.plaintext) or response.tag != chunk.tag:
                raise ProtocolError('Malformed chunk decryption response.')
            plaintext.extend(response.ciphertext)
            responses.append(response)
            if progress:
                progress(index+1, len(requests))
        return bytes(plaintext), responses
    finally:
        # No partially authenticated message is returned to the caller/UI.
        plaintext[:] = b'\0' * len(plaintext)
