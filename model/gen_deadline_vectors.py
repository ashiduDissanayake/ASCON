#!/usr/bin/env python3
"""Deterministic independent-reference vectors; generated files stay in build/."""
import random
from pathlib import Path
from refmodel import encrypt, decrypt_raw
from gen_vectors import pack_beats

ROOT=Path(__file__).resolve().parents[1]
def record(direction,key,nonce,ad,data,tag,out,computed,ok):
    fields=[str(direction),key.hex(),nonce.hex(),str(len(ad))]
    fields += [f'{b:032x}' for b in pack_beats(ad)]
    fields += [str(len(data))]+[f'{b:032x}' for b in pack_beats(data)]
    fields += [tag.hex()]+[f'{b:032x}' for b in pack_beats(out)]
    return ' '.join(fields+[computed.hex(),str(ok)])+'\n'

def cases(rng,a,m,negative=False):
    key=rng.randbytes(16);nonce=rng.randbytes(16);ad=rng.randbytes(a);pt=rng.randbytes(m)
    ct,tag=encrypt(key,nonce,ad,pt)
    yield record(0,key,nonce,ad,pt,bytes(16),ct,tag,1)
    yield record(1,key,nonce,ad,ct,tag,pt,tag,1)
    if negative:
        flip=lambda b: bytes([b[0]^1])+b[1:]
        for kk,nn,aa,cc,tt in [(key,nonce,ad,ct,flip(tag)),
                               (flip(key),nonce,ad,ct,tag),
                               (key,flip(nonce),ad,ct,tag),
                               (key,nonce,flip(ad),ct,tag),
                               (key,nonce,ad,flip(ct),tag)]:
            out,computed=decrypt_raw(kk,nn,aa,cc)
            assert computed!=tt
            yield record(1,kk,nn,aa,cc,tt,out,computed,0)

def main():
    target=ROOT/'build';target.mkdir(exist_ok=True)
    rng=random.Random(0xA5C04)
    count=0
    with (target/'bounded_cases.vec').open('w') as stream:
        for m in range(1,257):
            for line in cases(rng,48,m,True):stream.write(line);count+=1
    print(f'Generated {count} buffered cases: every length 1..256, both directions, five tampering classes.')
    lengths=list(range(34))+[48,64,127,128,129,143,144,145,159,160,255,256]
    count=0
    with (target/'fast_cases.vec').open('w') as stream:
        for a in range(65):
            for m in lengths:
                for line in cases(rng,a,m):stream.write(line);count+=1
    print(f'Generated {count} generic-core cases including empty streams and every AD length 0..64.')
if __name__=='__main__':main()
