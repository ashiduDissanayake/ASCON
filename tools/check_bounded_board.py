#!/usr/bin/env python3
"""Board smoke check for ASC4; the board must already contain the new bitstream."""
import argparse
import hashlib
import json
import secrets
import sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop interface'))
sys.path.insert(0,str(ROOT/'model'))
from ascon_app.protocol import Request,ProtocolError
from ascon_app.transport import SerialTransport
from refmodel import encrypt

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--bitstream',type=Path,default=ROOT/'build/vivado/ascon_basys3_bounded_top/ascon_gateway.bit')
    args=parser.parse_args()
    if not args.bitstream.is_file():parser.error('build/program the bounded bitstream first; supply its path with --bitstream')
    results=[];key=secrets.token_bytes(16);ad=bytes(range(48));transport=SerialTransport(args.port)
    try:
        for size in [1,16,17,128,256]:
            nonce=secrets.token_bytes(16);plain=secrets.token_bytes(size)
            cipher,tag=encrypt(key,nonce,ad,plain)
            for direction in [False,True]:
                response=transport.run(Request(key,nonce,ad,cipher if direction else plain,direction,tag if direction else b''))
                if response.ciphertext!=(plain if direction else cipher) or response.tag!=tag:
                    raise RuntimeError(f'board/reference mismatch: {size} bytes, decrypt={direction}')
                if response.execution_cycles!=59+8*(size//16):
                    raise RuntimeError('missing or wrong ASC4 execution timing')
                results.append({'bytes':size,'decrypt':direction,'cycles':response.execution_cycles,
                                'nominal_execution_us':response.execution_cycles/100})
        changed=bytes([tag[0]^1])+tag[1:]
        try:transport.run(Request(key,nonce,ad,cipher,True,changed))
        except ProtocolError as exc:
            if 'Authentication failed' not in str(exc):raise
        else:raise RuntimeError('changed tag was accepted')
    finally:transport.close()
    print(json.dumps({'status':'board/reference exchange passed',
        'timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'operator_supplied_bitstream_sha256':hashlib.sha256(args.bitstream.read_bytes()).hexdigest(),
        'clock_frequency_is_declared_not_independently_measured':True,
        'maximum_cycles':max(row['cycles'] for row in results),
        'bad_tag_rejected':True,'cases':results},indent=2))

if __name__=='__main__':main()
