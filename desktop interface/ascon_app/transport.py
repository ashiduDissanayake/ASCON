"""UART v3 stop-and-wait input and block-record output. No Tk dependency."""
import time
from .protocol import Response, ProtocolError, encode_request, decode_record

TIMEOUT = 3.0  # Per-record inactivity deadline, NOT a whole-message deadline.


def list_ports():
    try:
        from serial.tools import list_ports as ports
    except ImportError:
        return []
    return [(p.device, p.description) for p in ports.comports()]


def write_all(stream, data, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    offset = 0
    while offset < len(data):
        count = stream.write(data[offset:])
        if not count or time.monotonic() >= deadline:
            raise TimeoutError('UART write stalled. Press btnC before reconnecting.')
        offset += count


def read_exact(stream, count, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    result = bytearray()
    while len(result) < count:
        if time.monotonic() >= deadline:
            raise TimeoutError(f'UART v3 timeout: {len(result)}/{count} record bytes. Check the streaming bitstream, press btnC and reconnect.')
        part = stream.read(count-len(result))
        if part:
            result.extend(part)
            deadline = time.monotonic() + timeout
    return bytes(result)


def exchange_stream(stream, request, timeout=TIMEOUT):
    """One input chunk is sent only when the FPGA explicitly requests it.

    Raw ciphertext/output blocks are accumulated here. The UI receives a result
    only after DONE; provisional decrypt blocks are quarantined in this function.
    Host storage is proportional to message size; 32-bit fields are not a promise
    that a GUI can practically hold a 4 GiB input and its hex representation.
    """
    stream.reset_input_buffer()
    write_all(stream, encode_request(request), timeout)
    kind, count, payload = decode_record(read_exact(stream, 19, timeout))
    if kind != 1 or count != 3 or payload[:4] != b'ASC3':
        raise ProtocolError('Wrong firmware/protocol: expected UART v3 ASC3 hello.')
    if payload[4:8] != b'\xff'*4 or payload[8:] != b'\x01'+b'\0'*7:
        raise ProtocolError('Wrong firmware capabilities: streaming provisional decryption required.')
    ad_offset = data_offset = 0
    output = bytearray()
    while True:
        kind, count, payload = decode_record(read_exact(stream, 19, timeout))
        if kind in (0x10, 0x11):
            if any(payload):
                raise ProtocolError('Malformed input grant.')
            source = request.ad if kind == 0x10 else request.plaintext
            offset = ad_offset if kind == 0x10 else data_offset
            if kind == 0x10 and data_offset:
                raise ProtocolError('AD requested after message data.')
            if kind == 0x11 and ad_offset != len(request.ad):
                raise ProtocolError('Data requested before all AD.')
            if count == 0 or count != min(16, len(source)-offset):
                raise ProtocolError('Invalid or excess input grant.')
            write_all(stream, source[offset:offset+count], timeout)
            if kind == 0x10:
                ad_offset += count
            else:
                data_offset += count
        elif kind in (0x12, 0x14):
            if kind != (0x14 if request.decrypt else 0x12):
                raise ProtocolError('Wrong output record type for this operation.')
            if ad_offset != len(request.ad):
                raise ProtocolError('Output arrived before AD was transferred.')
            if not 1 <= count <= 16 or count != min(16, len(request.plaintext)-len(output)):
                raise ProtocolError('Invalid output block length.')
            if len(output)+count > data_offset:
                raise ProtocolError('Output exceeds submitted input.')
            if any(payload[count:]):
                raise ProtocolError('Nonzero padding in output record.')
            output.extend(payload[:count])
        elif kind == 0x13:
            if count != 16 or ad_offset != len(request.ad) or data_offset != len(request.plaintext) or len(output) != len(request.plaintext):
                raise ProtocolError('Premature or malformed completion record.')
            if request.decrypt and payload != request.tag:
                raise ProtocolError('Decryption completion tag differs from the supplied tag.')
            return Response(bytes(output), payload, b'')
        else:
            raise ProtocolError(f'Unexpected UART record type 0x{kind:02x}.')


class SerialTransport:
    def __init__(self, port):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError('Install pyserial: python -m pip install -r requirements.txt') from exc
        self.stream = serial.Serial(port=port, baudrate=115200, bytesize=8,
                                    parity='N', stopbits=1, timeout=0.1,
                                    write_timeout=1, xonxoff=False,
                                    rtscts=False, dsrdtr=False)

    def run(self, request):
        return exchange_stream(self.stream, request)

    def close(self):
        self.stream.close()


class DemoTransport:
    """Software computation only; serial byte transport is tested separately."""
    def run(self, request):
        from .reference_ascon import ascon_encrypt, ascon_decrypt
        if request.decrypt:
            plain = ascon_decrypt(request.key, request.nonce, request.ad, request.plaintext+request.tag)
            if plain is None:
                raise ProtocolError('Authentication failed. No plaintext was released.')
            return Response(plain, request.tag, b'')
        result = ascon_encrypt(request.key, request.nonce, request.ad, request.plaintext)
        return Response(result[:-16], result[-16:], b'')

    def close(self):
        pass
