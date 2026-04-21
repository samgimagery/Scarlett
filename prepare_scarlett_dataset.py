#!/usr/bin/env python3
"""
Prepare Scarlett Johansson audiobook dataset for Qwen3-TTS fine-tuning.

Source: Alice in Wonderland audiobook read by Scarlett Johansson
- Skip first 90 seconds (intro/jingle)
- Segment into 5-15 second training clips
- Convert to 24kHz mono WAV
- Transcribe with Whisper for ground-truth text
- Output train_raw.jsonl for mlx-tune
"""

import os
import json
import subprocess
import argparse

# Paths
SOURCE = os.path.expanduser("~/Media/voices/scarlett_audiobook/scarlett_alice_raw.wav")
OUTPUT_DIR = os.path.expanduser("~/Media/voices/scarlett_audiobook/clips")
START_SEC = 90  # Skip intro/jingle
CLIP_MIN_SEC = 5
CLIP_MAX_SEC = 15
TARGET_SR = 24000


def segment_audio(source, output_dir, start_sec, clip_min, clip_max, sr=24000):
    """Split source audio into clips of clip_min to clip_max seconds."""
    os.makedirs(output_dir, exist_ok=True)
    
    # Get duration
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", source],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)
    total_sec = float(info["format"]["duration"])
    usable_sec = total_sec - start_sec
    
    print(f"Total: {total_sec:.0f}s ({total_sec/3600:.2f}h)")
    print(f"Usable: {usable_sec:.0f}s ({usable_sec/60:.1f}min) after skipping {start_sec}s intro")
    
    # Calculate number of clips targeting ~10s each
    target_clip_len = 10  # seconds
    num_clips = int(usable_sec / target_clip_len)
    print(f"Will create ~{num_clips} clips of ~{target_clip_len}s each")
    
    clips = []
    t = start_sec
    idx = 0
    
    while t + clip_min < total_sec:
        # Vary clip length between min and max for diversity
        # Use a pattern: 8, 10, 12, 10, 8, 15, 10, ... 
        lengths = [8, 10, 12, 10, 9, 14, 10, 11, 8, 13]
        clip_len = lengths[idx % len(lengths)]
        clip_len = max(clip_min, min(clip_len, clip_max))
        
        # Don't go past the end
        if t + clip_len > total_sec:
            clip_len = total_sec - t
            if clip_len < clip_min:
                break
        
        out_path = os.path.join(output_dir, f"scarlett_{idx:04d}.wav")
        
        # Extract and convert to 24kHz mono
        subprocess.run([
            "ffmpeg", "-y", "-v", "quiet",
            "-ss", str(t),
            "-t", str(clip_len),
            "-i", source,
            "-ar", str(sr),
            "-ac", "1",
            out_path
        ], check=True)
        
        clips.append({
            "path": out_path,
            "start": t,
            "duration": clip_len,
            "index": idx,
        })
        
        t += clip_len
        idx += 1
    
    print(f"\nCreated {len(clips)} clips")
    total_dur = sum(c["duration"] for c in clips)
    print(f"Total clip duration: {total_dur:.0f}s ({total_dur/60:.1f}min)")
    
    return clips


def transcribe_clips(clips, model="small"):
    """Transcribe clips using faster-whisper."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper not installed. Run: pip install faster-whisper")
        print("Skipping transcription — you'll need to provide text manually.")
        return None
    
    print(f"\nTranscribing {len(clips)} clips with faster-whisper ({model})...")
    whisper = WhisperModel(model, device="cpu", compute_type="int8")
    
    transcripts = []
    for i, clip in enumerate(clips):
        path = clip["path"]
        segments, info = whisper.transcribe(path, language="en", beam_size=5)
        text = " ".join(s.text.strip() for s in segments).strip()
        
        if not text:
            print(f"  [{i+1}/{len(clips)}] EMPTY — skipping")
            os.remove(path)
            continue
        
        transcripts.append({
            "path": path,
            "text": text,
            "duration": clip["duration"],
        })
        
        if (i + 1) % 50 == 0 or i < 5 or i == len(clips) - 1:
            print(f"  [{i+1}/{len(clips)}] {os.path.basename(path)}: {text[:80]}...")
    
    print(f"\nTranscribed {len(transcripts)} clips (skipped {len(clips) - len(transcripts)} empty)")
    return transcripts


def build_jsonl(transcripts, output_dir):
    """Build train_raw.jsonl for mlx-tune."""
    jsonl_path = os.path.join(os.path.dirname(output_dir), "train_raw.jsonl")
    
    entries = []
    for t in transcripts:
        entries.append({
            "audio_path": t["path"],
            "text": t["text"],
            "speaker": "scarlett_johansson",
        })
    
    with open(jsonl_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    
    print(f"\nWrote {len(entries)} entries to {jsonl_path}")
    total_dur = sum(t["duration"] for t in transcripts)
    print(f"Total training audio: {total_dur:.0f}s ({total_dur/60:.1f}min)")
    return jsonl_path


def main():
    parser = argparse.ArgumentParser(description="Prepare Scarlett audiobook dataset")
    parser.add_argument("--skip-transcribe", action="store_true", help="Skip transcription (just segment)")
    parser.add_argument("--max-clips", type=int, default=0, help="Max clips (0 = all)")
    parser.add_argument("--clip-count", type=int, default=0, help="Target number of clips (overrides length calc)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Scarlett Johansson Audiobook Dataset Preparation")
    print("=" * 60)
    print(f"Source: {SOURCE}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Skip first: {START_SEC}s")
    print()
    
    # Step 1: Segment
    clips = segment_audio(SOURCE, OUTPUT_DIR, START_SEC, CLIP_MIN_SEC, CLIP_MAX_SEC)
    
    if args.max_clips and args.max_clips < len(clips):
        print(f"\nLimiting to {args.max_clips} clips")
        clips = clips[:args.max_clips]
    
    if args.skip_transcribe:
        print("\nSkipping transcription (--skip-transcribe)")
        print(f"Clips ready in: {OUTPUT_DIR}")
        return
    
    # Step 2: Transcribe
    transcripts = transcribe_clips(clips)
    if transcripts is None:
        return
    
    # Step 3: Build JSONL
    jsonl_path = build_jsonl(transcripts, OUTPUT_DIR)
    
    print(f"\n✅ Dataset ready!")
    print(f"   Clips: {OUTPUT_DIR}/")
    print(f"   Labels: {jsonl_path}")
    print(f"\nNext: Run finetune_her.py with this dataset")


if __name__ == "__main__":
    main()