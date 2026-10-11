"""Transaction orchestration and portable result export."""
from datetime import datetime, timezone
import json
import time
from .messages import MessageDecryptRequest, encrypt_message, decrypt_message



def run_operation(transport, request, source, progress=None):
    start = time.perf_counter()
    if isinstance(request, MessageDecryptRequest) or len(request.plaintext) > 256:
        if request.decrypt and not isinstance(request, MessageDecryptRequest):
            raise ValueError('Large-message decryption requires the exported chunked message JSON, including every nonce and tag.')
        if request.decrypt:
            plaintext, responses = decrypt_message(transport, request, progress)
            envelope = request.envelope
        else:
            envelope, responses = encrypt_message(transport, request, progress)
            plaintext = None
        times = [r.execution_cycles/r.execution_clock_hz*1_000_000
                 if r.execution_cycles is not None and r.execution_clock_hz else None for r in responses]
        return {
            'format': envelope['format'], 'algorithm': 'Ascon-AEAD128',
            'source': source, 'operation': 'decrypt' if request.decrypt else 'encrypt',
            'authentication': 'verified' if request.decrypt else 'tags generated',
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'message': envelope, 'chunk_count': len(responses),
            'nonce_hex': envelope['base_nonce_hex'],
            'associated_data_hex': envelope['associated_data_hex'],
            'ciphertext_hex': ''.join(c['ciphertext_hex'] for c in envelope['chunks']),
            'plaintext_hex': plaintext.hex() if plaintext is not None else None,
            'tag_hex': None, 'plaintext_bytes': envelope['plaintext_bytes'],
            'round_trip_ms': round((time.perf_counter()-start)*1000, 3),
            'execution_us': None,
            'chunk_execution_cycles': [r.execution_cycles for r in responses],
            'chunk_execution_us': times,
            'total_execution_us': sum(times) if all(t is not None for t in times) else None,
        }
    response = transport.run(request)
    return {
        'format': 'basys3-ascon-result-v3',
        'algorithm': 'Ascon-AEAD128',
        'source': source,
        'operation': 'decrypt' if request.decrypt else 'encrypt',
        'authentication': 'verified' if request.decrypt else 'tag generated',
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'nonce_hex': request.nonce.hex(),
        'associated_data_hex': request.ad.hex(),
        'ciphertext_hex': request.plaintext.hex() if request.decrypt else response.ciphertext.hex(),
        'plaintext_hex': response.ciphertext.hex() if request.decrypt else None,
        'tag_hex': response.tag.hex(),
        'response_hex': response.raw.hex(),
        'plaintext_bytes': len(request.plaintext),
        'round_trip_ms': round((time.perf_counter()-start)*1000, 3),
        'execution_cycles': response.execution_cycles,
        'execution_clock_hz': response.execution_clock_hz,
        'execution_us': (response.execution_cycles/response.execution_clock_hz*1_000_000
                         if response.execution_cycles is not None else None),
    }


def save_result(path, result):
    # Deliberately excludes the secret key and plaintext from exported files.
    with open(path, 'w', encoding='utf-8') as stream:
        json.dump({k: v for k, v in result.items() if k not in ('plaintext_hex', 'response_hex')}, stream, indent=2)
        stream.write('\n')
