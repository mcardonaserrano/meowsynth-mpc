# What MeowSynth.dll is, and how this port reads it

MeowSynth 1.0 (knobster.org, 2009) is a SynthEdit 1.0 plugin: a 32-bit Windows DLL (`se_vst.dll`, export `main`)
that carries the SynthEdit runtime, its built-in modules, and the author's project as resource `SE1`/165.
It holds **no samples**: the meow is a ramp oscillator through a resonant low-pass whose cutoff follows the
note's own loudness.

## The embedded project
- `SE1` is scrambled: a byte is XORed with `0x83`, then two bytes are skipped, unless the plain byte was odd,
  in which case the next byte is XORed too (`re/extract_assets.py`, `re/parse_se.py`).
- Inside: five add-on modules as DLLs (`Int To List2`, `KDL Volts2Hz`, `KDL Volts2GuiInt`, `BPM Clock2`,
  `DH_MultiFilter2`), the skin's PNGs, and the project as an MFC `CArchive` object graph.
- `re/parse_se.py` walks that graph (class layouts worked out from the data; it ends exactly at the end of the
  resource) and `re/netlist.py` prints it as a netlist: `re/netlist.txt`.
- The patch manager names five programs: Clear cat, Old cat, March cat, Catband, Gospel cats. Sliders keep 128
  values each; the filter block's sliders (Cutoff 4.3, Q 7.8, Filter Type LP, Dry/Wet +5, follower Attack 4.8 /
  Decay 10, Gain 10, EnvMod 10) and Portamento (5.56) hold one value for all of them.

## Module behaviour, read from the code (addresses are in MeowSynth.dll unless noted)
Audio and control values are volts / 10 (10 V = 1.0).

| Module | What the code does | Where |
|---|---|---|
| ADSR | Linear segments. A rate pin of V volts takes `2^(V - 6.667)` s for a full 0..10 V sweep (0 V = 9.8 ms, 10 V = 10 s). Output = level x Overall Level. | `0x10081330`, `0x10080ff0`, `0x10081550` |
| VCA, "Exponential" | gain = `1 - (1 - e^(-3(1-v))) / (1 - e^-3)`, faded to 0 below v = 0.001; 512-entry table | `0x100c28a0` (curve list at `0x1015471c`) |
| Peak Follower | on `abs(in)`: `env = x + (env - x) * c`, attack c when x > env, else decay c; `c = exp(-100 / (pin * SR))`, pin floor 0.001 (so a pin of V volts is a time constant of V ms) | `0x100b7100`, `0x100b6d80` |
| X-Mix, "Equal Power" | gain A = `sin(m * pi/2)`, gain B = `sin((1-m) * pi/2)`, m = (mix + 5 V) / 10 V; +5 V = input A | `0x100b33b0` |
| Level Adj | a x b | `0x100a5f70` |
| Multiply / Divide | in volts: a x b x 10, a / b / 10 | `0x10097db0`, `0x10097480` |
| Midi to CV | pitch 1 V/oct, A4 = 5 V; velocity / 127; bender = +-Bend Range semitones, glided over 1/60 s; portamento of V volts = a linear glide of `2^((V - 2) - 6.667)` s | `0x100a1b60`, `0x100a1ef0`, `0x100a1fd0` |
| Oscillator | list "Sine, Saw, Ramp, Triangle, Pulse, White Noise, Pink Noise"; +-5 V out; pin 4 = Sync (phase reset), pin 6 = Freq Scale (1 V/oct or 1 V/kHz) | strings at `0x10152cd8`.. |
| BPM Clock2, Tempo Out | host tempo x 0.1 as a sample value, i.e. volts = BPM (100 when the host gives none) | `clock2.sem` `0x10001465` |
| DH_MultiFilter2 | pins: in, Freq/Pitch, Q/Res, Type (LP,HP,BP1,BP2,Notch), Gain Compensation, Stages, out, Input Mode. Pitch mode: `440 * 2^(V-5)` Hz, -2..12 V, capped at 0.99 Nyquist. Res mode: `Q = exp(0.05 * exp(4.5 * r)) - 0.6`. RBJ biquads, direct form I, coefficients refreshed every 4 samples. One-stage gain compensation: a row of factors by `2 ln Q` times `exp(0.2759 - 0.2461x - 0.0144x^2 - 0.0041x^3)`, x = ln Q | `dh_multifilter2.sem` `0x100011a0`, `0x10002210`, `0x100023e0`, `0x10001c10` |

## The patch (re/netlist.txt)
- Voice: Midi to CV -> Oscillator #1e1 (Ramp, Sync <- Gate) -> VCA <- ADSR (A,D,S,R <- sliders "M","O","E","W";
  level <- Velocity). Oscillator #29b (White Noise) -> VCA <- ADSR (0, 5, 7, 4 V). X-Mix(noise, osc), mix <- "Noise"
  (-5..-4 V).
- Filter container: both channels get the same signal; Peak Follower listens to their sum (2x). Filter pitch =
  Cutoff + follower x EnvMod. X-Mix(filter, dry) <- Dry/Wet, then VCA <- Gain.
- Vibrato: Tempo Sync LFO (sine, 1 V/kHz, pitch = BPM / (60000 x division), division 16..0.0625 beats) -> VCA <-
  ADSR (A <- "Vibrato Attack", 5, 7, 4 V; level <- "Vibrato Amount") -> added to the oscillator's pitch.
- Chorus container (set to ignore program changes): two Delay2 (0.06 s), modulation = Min (1.15 V) + Depth
  (4.19 V) x (sine LFO + 5 V), LFO at -9.07 V = 0.0256 Hz, the second LFO 0.325 V x 5 V of phase later;
  X-Mix(delay, dry) <- "Chorus".
- Cat: the amp ADSR's output -> KDL Volts2GuiInt (40 Hz, truncate) -> frame of baks.png (12 frames).
- POLYCAT -> Midi to CV Mono Mode (1 = mono; Retrigger on, last-note priority). P.BEND list -> Bend Range.

## Checked against the DLL itself (re/ab/)
The DLL runs under Wine on a Mac (a Wineskin/CrossOver engine handles 32-bit code), hosted by a small
freestanding VST2 host (`re/ab/host.c`, linked by `re/ab/pelink.py`). `re/ab/ab.py` plays the same notes through
it and through this port's engine and compares them; the `t_*.py` scripts are the comparisons. Results:
- Single notes, every program, across the keyboard and velocities: level within about 0.1 dB, harmonics within
  about 0.2 dB, the same filter sweep.
- Portamento only happens between overlapping notes (a key still down); a note after a gap starts on pitch.
  Releasing the upper of two held keys in mono glides back and retriggers the envelope.
- Polyphony is 6 voices.
- The Chorus container's four knobs have values in the first program only (Depth 4.19, Min 1.15, Rate -9.07,
  Phase 0.33); the other programs hold zeros, so there the delay is 0 samples and the Chorus slider only mixes
  the signal with itself: louder by up to 3 dB, no chorus, identical left and right. With the first program's
  values the delay sweeps 304..1412 samples over 39 s, the right channel 5.9 degrees behind the left.
- Vibrato: rate = tempo / (60 x division) Hz (32 Hz for "1/16" at 120 BPM), depth as computed.
- P.BEND: the bend is the list **index** in semitones (the box reading "12" bends 11, "1" bends none), and a
  program change does not move it.

## Where this port departs from the original
- P.BEND bends what the box says (1..12 semitones); like the original, programs leave it alone.
- The oscillator is band-limited with polyBLEP instead of SynthEdit's wavetables (no measurable difference in
  the comparisons above), and peaks above 0.75 of full scale are rounded off instead of clipping.
- When more than 6 notes are held, which note gives up its voice can differ.
- The filter block and the follower are on a second page; the original keeps them hidden.
