# Scarlett Voice Speed + Stability Findings

REQ-123 tested speed, stability, and delay placement for Scarlett’s live voice layer.

## Reports

- Main broad run: `reports/voice_speed/voice_speed_matrix_20260506-060522.md`
- Correct direct-TTS venv run: `reports/voice_speed/voice_speed_matrix_20260506-060919.md`

## What we tested

- 10,000 in-process service-tile selections.
- 150 HTTP service-tile catalog calls.
- 230 `/ask` calls with voice metadata.
- 1,500 cached WAV file reads.
- 20 current Mind Vault `/api/voice` Scarlett/Qwen FR calls.
- 10 CSM filler HTTP calls.
- Direct Qwen FR LoRA calls inside the correct `.voice-clone-env`.
- Kokoro FR fast path attempt, which is currently not viable in this venv because the optional `misaki` dependency/output path is missing.

## Headline result

**The fast production path is not faster live generation. It is prebuilt tile playback plus delayed full answer.**

The service tile decision layer is effectively free. Cached WAV access is effectively free. Live Qwen generation is too slow and variable to block first audio.

## Timing evidence

### Tile decision / metadata

- `tile_select_inprocess`: median ~0 ms, p90 ~0 ms, max ~0.4 ms.
- `service_tiles_http_catalog`: median 3.5–4.9 ms, p90 4.4–5.3 ms.

This is stable enough to run before audio playback.

### Cached / pre-recorded audio

- `cached_wav_file_read`: 1,500 attempts.
- median ~0 ms.
- p90 ~0 ms.
- max 0.5 ms.

This means once tile audio exists on disk, file access is not the bottleneck. Browser/network decode and playback scheduling will dominate, not the server read.

### `/ask` with voice metadata

- 230 attempts.
- median 4.7 ms.
- p90 5.8 s.
- max 17.4 s.

Interpretation: deterministic/local cases are extremely fast, but RAG/generation cases can be slow. This is acceptable only if Scarlett starts speaking from a tile while the full answer cooks.

### Current Scarlett `/api/voice` live Qwen FR path

- 20 attempts.
- median 3.1 s.
- p90 4.1 s.
- max 4.7 s.

Correct venv direct generation:

- median 3.4 s.
- p90 5.6 s.
- max 6.4 s.

This is too slow for first audio. It is acceptable for background full-answer generation after a tile has already played.

### CSM filler

- median ~2.28 s.
- p90 ~2.55 s.

Current CSM HTTP filler is not fast enough to be the first-audio answer on its own. It may still be useful if warmed/streamed differently, but the cached tile bank beats it decisively.

## Stability finding

The stable path is:

1. classify intent / select tile
2. play cached tile immediately
3. run `/ask` in parallel
4. if `/ask` returns quickly, continue naturally
5. if `/ask` is slow, use an intentional delay/filler tile at the right moment
6. only generate live audio for content that is not already tiled

The unstable path is:

1. wait for RAG/generation
2. wait for live TTS
3. then speak

That produces dead air and unpredictable delays.

## Delay placement policy

Speed should feel calm, not frantic. The target is **responsive but composed**.

### Immediate zone: 0–300 ms

Use for:

- greeting
- yes/no receipts
- “Oui?” after interruption
- simple repair: “Je n’ai pas bien entendu…”

This should be cached audio only.

### Human beat: 300–700 ms

Use for:

- acknowledgement before lookup
- “Parfait — je regarde…”
- “Oui — je vais d’abord situer…”

This is the sweet spot for premium voice. It feels alive without feeling robotic.

### Thinking beat: 700–1,500 ms

Use when:

- retrieval is running
- answer needs facts
- user asked something broad

Play a lookup tile, not silence.

### Long answer bridge: 1,500–3,000 ms

If the answer is still cooking, use a second bridge tile:

- “Je veux te répondre proprement, je vérifie le bon parcours.”
- “Je regarde le repère exact pour ne pas te donner une mauvaise info.”

This should be rare but intentional.

### Beyond 3,000 ms

Do not sit silently. Either:

- continue with a partial deterministic answer,
- ask a clarifying question,
- or offer a handoff path.

## Best production architecture

For the Live Voice Add-On:

1. Per-business tile bank is generated/recorded at deployment time.
2. Runtime tile selection happens locally in milliseconds.
3. Audio file starts immediately.
4. Brain/RAG runs in parallel.
5. Live TTS is used only for non-tiled specifics.
6. New production misses become candidate tiles.

## Improvement opportunities

1. **Generate actual AMS tile asset bank** into the declared `asset_id` paths.
2. **Wire voice shell to play `voice.asset_id` first**, before waiting for answer completion.
3. **Run browser/WebSocket playback timing**: server read is ~0 ms, but real first audible sound depends on WS/browser scheduling.
4. **Add a two-tile delay ladder**: first tile at 300–700 ms, bridge tile around 1.5–2.0 s if still waiting.
5. **Keep Qwen FR LoRA for quality**, but never block first audio on it.
6. **Treat Kokoro as currently blocked** for FR fast fallback until dependency/output issue is fixed; even then it is a quality tradeoff, not the premium path.
7. **Investigate CSM streaming/warm server separately**. Current HTTP generation is too slow for first audio.

## Product conclusion

The promising part is not “make TTS faster.”

The promising part is **place the delay where a human would place it**.

Scarlett should answer instantly when the social moment is obvious, pause gracefully when thinking is appropriate, and only expose live generation latency after she has already acknowledged the person.
