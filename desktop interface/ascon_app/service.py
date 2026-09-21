"""Transaction orchestration and portable result export."""
from datetime import datetime, timezone
import json
import time



def run_operation(transport, request, source):
    start = time.perf_counter()
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
    }


def save_result(path, result):
    # Deliberately excludes the secret key and plaintext from exported files.
    with open(path, 'w', encoding='utf-8') as stream:
        json.dump({k: v for k, v in result.items() if k not in ('plaintext_hex', 'response_hex')}, stream, indent=2)
        stream.write('\n')
