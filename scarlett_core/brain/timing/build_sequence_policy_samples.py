#!/usr/bin/env python3
"""Build sequence-policy sample reels for Scarlett."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scarlett_core.brain.timing.sequence_policy import build_sequence, sequence_manifest

OUT = Path('/Users/samg/Media/voices/scarlett_micro_bank/v0/sequence')
OUT.mkdir(parents=True, exist_ok=True)

GREETING = '/Users/samg/Media/voices/tmp/scarlett_fr_lora_1778120504524/audio_000.wav'
ORIENT = '/Users/samg/Media/voices/tmp/scarlett_fr_lora_1778120509094/audio_000.wav'
PRICE = '/Users/samg/Media/voices/tmp/scarlett_fr_lora_1778120511602/audio_000.wav'

def render(name: str, sequence):
    manifest_path = OUT / f'{name}.json'
    manifest_path.write_text(json.dumps(sequence_manifest(sequence), indent=2, ensure_ascii=False), encoding='utf-8')
    concat_path = OUT / f'{name}.concat.txt'
    lines = [f"file '{piece.path}'" for piece in sequence if piece.path]
    concat_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    audio_path = OUT / f'{name}.m4a'
    subprocess.run([
        'ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat_path),'-c:a','aac','-b:a','144k',str(audio_path)
    ], check=True)
    print(audio_path)

# Caller disclosed they are starting in massage. Receipt belongs before orientation.
seq_receipt_orientation = build_sequence([
    {'asset_id':'tile-ams-int-006','path':ORIENT,'text':"Parfait — si tu commences, on regarde d'abord le Niveau 1.",'act':'orientation','word_count':9},
    {'asset_id':'tile-ams-int-011','path':PRICE,'text':'Le Niveau 1 coûte deux mille neuf cent quatre-vingt-quinze dollars.','act':'answer','word_count':10},
], previous_act='caller_disclosure', next_act='orientation', same_turn=False, caller_waiting=True)
render('policy_receipt_orientation_price', seq_receipt_orientation)

# Greeting and answer should not be same-turn connected with a hum.
seq_greeting_then_orientation = build_sequence([
    {'asset_id':'tile-ams-int-001','path':GREETING,'text':'Bonjour, je suis Scarlett.','act':'greeting','word_count':4},
    {'asset_id':'tile-ams-int-006','path':ORIENT,'text':"Parfait — si tu commences, on regarde d'abord le Niveau 1.",'act':'orientation','word_count':9},
], previous_act='greeting', next_act='orientation', same_turn=True, caller_waiting=True)
render('policy_no_hum_after_greeting', seq_greeting_then_orientation)
