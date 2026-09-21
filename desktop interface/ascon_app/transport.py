"""Byte transport. All hardware I/O runs in the application's worker thread."""
import time


def list_ports():
    try:
        from serial.tools import list_ports as ports
    except ImportError:
        return []
    return [(p.device, p.description) for p in ports.comports()]


def exchange_stream(stream, packet, timeout=3.0):
    """Handle fragmented reads/writes. Never silently retry an encryption."""
    stream.reset_input_buffer()
    deadline = time.monotonic() + timeout
    written = 0
    while written < len(packet):
        count = stream.write(packet[written:])
        if not count or time.monotonic() >= deadline:
            raise TimeoutError('Request write incomplete. Press FPGA btnC before reconnecting.')
        written += count
    received = bytearray()
    while len(received) < 34:
        if time.monotonic() >= deadline:
            raise TimeoutError(f'Received {len(received)}/34 bytes. Check bitstream/port, press btnC, then reconnect.')
        received.extend(stream.read(34-len(received)))
    return bytes(received)


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

    def exchange(self, packet):
        return exchange_stream(self.stream, packet)

    def close(self):
        self.stream.close()


class DemoTransport:
    """Explicit software demonstration; never presented as an FPGA result."""
    def exchange(self, packet):
        from .reference_ascon import ascon_encrypt, ascon_decrypt
        if len(packet) not in (68, 84) or packet[0] != 0xA5 or packet[1] not in (1, 2):
            raise ValueError('Bad demo request')
        ad_len, pt_len = packet[2:4]
        if packet[1] == 2:
            plaintext = ascon_decrypt(packet[4:20], packet[20:36],
                                      packet[36:36+ad_len], packet[52:52+pt_len] + packet[68:84])
            if plaintext is None:
                return b'\x5a\x03' + bytes(32)
            return b'\x5a\x00' + plaintext.ljust(16, b'\0') + packet[68:84]
        combined = ascon_encrypt(packet[4:20], packet[20:36],
                                 packet[36:36+ad_len], packet[52:52+pt_len])
        return b'\x5a\x00' + combined[:-16].ljust(16, b'\0') + combined[-16:]

    def close(self):
        pass
