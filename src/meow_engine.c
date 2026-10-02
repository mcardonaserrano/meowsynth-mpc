/* MeowSynth for MPC OS: a native re-creation of knobster's MeowSynth 1.0 (a SynthEdit VST2 for Windows).
 *
 * The Windows DLL cannot run on the MPC (x86 code, Win32 GUI), so this engine rebuilds its patch from the
 * SynthEdit project embedded in the DLL (re/netlist.txt) and the module code it links (re/NOTES.md):
 *
 *   Midi to CV -> Oscillator (ramp, phase reset on gate) -> VCA <- ADSR "M,O,E,W" (level = velocity)
 *              -> Oscillator (white noise)               -> VCA <- ADSR (fixed)
 *   X-Mix (noise | osc) -> DH_MultiFilter2 (1 biquad, cutoff = Cutoff + Peak Follower(2 x signal) * EnvMod)
 *                       -> X-Mix (filter | dry) -> VCA (Gain) -> Chorus (2 modulated delays, X-Mix) -> out
 *   Tempo Sync LFO (sine) -> VCA <- ADSR (Vibrato Attack, level = Vibrato Amount) -> oscillator pitch
 *
 * Voltages are SynthEdit's: 10 V = 1.0, pitch is 1 V/octave with 5 V = A440, audio oscillators are +-5 V.
 * Checked note for note against the DLL itself running under Wine (re/ab/): levels within a few tenths of
 * a dB, the same pitch glides, vibrato, chorus and program behaviour.
 * Engine contract: wrapper/engine.h (44.1 kHz, interleaved int16 stereo, 128-frame blocks). */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "engine.h"

#define SR 44100.0f
#define NVOICES 6                /* the original's polyphony */
#define CTRL 4                 /* pitch and filter coefficients update every 4 samples, as DH_MultiFilter2 does */
#define DELAY_LEN 4096         /* >= 0.06 s (the chorus Delay2's "Delay Time") */
#define VCA_N 512
#define PI_F 3.14159265358979f
#define OUT_TRIM 1.0f          /* the original's level; peaks past 0.75 are rounded off instead of clipping */

enum {
    P_PRESET, P_M, P_E, P_O, P_W, P_VIB_AMT, P_VIB_ATK, P_VIB_SPEED, P_PORTA, P_NOISE, P_CHORUS, P_BEND, P_POLY,
    P_CUTOFF, P_RESO, P_ENVMOD, P_FTYPE, P_FOL_ATK, P_FOL_DEC, P_FMIX, P_GAIN, NP
};

/* Keys and ranges match params.json (the VST parameter order). nopts > 0: an option list (value = index). */
static const struct { const char *key; float min, max, def; int nopts, integer; } PD[NP] = {
    [P_PRESET]    = {"preset",    0, 4,   0,      5, 1},
    [P_M]         = {"env_m",     0, 10,  2.9f,   0, 0},   /* "M": ADSR attack  */
    [P_E]         = {"env_e",     0, 10,  2.1f,   0, 0},   /* "E": ADSR sustain */
    [P_O]         = {"env_o",     0, 10,  7.2f,   0, 0},   /* "O": ADSR decay   */
    [P_W]         = {"env_w",     0, 10,  4.3168f, 0, 0},  /* "W": ADSR release */
    [P_VIB_AMT]   = {"vib_amt",   0, 10,  0,      0, 0},
    [P_VIB_ATK]   = {"vib_atk",   0, 10,  10,     0, 0},
    [P_VIB_SPEED] = {"vib_speed", 0, 9,   7,      10, 1},
    [P_PORTA]     = {"porta",     0, 100, 26,     0, 0},   /* the original slider's 4..10 V as 0..100 % */
    [P_NOISE]     = {"noise",     0, 100, 0,      0, 0},   /* X-Mix -5..-4 V as 0..100 % */
    [P_CHORUS]    = {"chorus",    0, 100, 0,      0, 0},   /* X-Mix -5..+5 V as 0..100 % */
    [P_BEND]      = {"bend",      1, 12,  12,     0, 1},
    [P_POLY]      = {"polycat",   0, 1,   0,      2, 1},
    [P_CUTOFF]    = {"cutoff",    0, 10,  4.3f,   0, 0},
    [P_RESO]      = {"reso",      0, 10,  7.8f,   0, 0},
    [P_ENVMOD]    = {"envmod",    0, 10,  10,     0, 0},
    [P_FTYPE]     = {"ftype",     0, 4,   0,      5, 1},
    [P_FOL_ATK]   = {"fol_atk",   0, 10,  4.8f,   0, 0},
    [P_FOL_DEC]   = {"fol_dec",   0, 10,  10,     0, 0},
    [P_FMIX]      = {"fmix",      0, 100, 100,    0, 0},   /* X-Mix -5..+5 V as 0..100 % */
    [P_GAIN]      = {"gain",      0, 10,  10,     0, 0},
};

/* The five named patches of the original's patch manager. The filter block (Cutoff..Gain) and
 * Portamento hold one value for every patch there, so a preset leaves them alone; so does P.BEND, which
 * the original does not move on a program change either. */
static const struct { float m, e, o, w, vib_amt, vib_atk; int speed; float noise, chorus; int poly; } PRESETS[5] = {
    /* Clear cat   */ {2.9f,  2.1f,  7.2f,  4.3168f, 0.0f,  10.0f, 7, 0,   0.0f,  0},
    /* Old cat     */ {3.4f,  3.35f, 7.55f, 4.4168f, 10.0f, 9.05f, 0, 100, 72.5f, 0},
    /* March cat   */ {3.35f, 2.55f, 7.6f,  4.2168f, 7.1f,  6.6f,  0, 27,  2.5f,  0},
    /* Catband     */ {2.4f,  4.05f, 6.95f, 3.8668f, 1.5f,  10.0f, 9, 100, 97.5f, 1},
    /* Gospel cats */ {2.3f,  4.0f,  6.8f,  2.9668f, 1.05f, 10.0f, 9, 5,   53.5f, 1},
};

/* Tempo Sync LFO "Divisions": the LFO period in beats (4 bar .. 1/16) */
static const float DIV_BEATS[10] = {16, 8, 4, 2, 1, 0.5f, 0.25f, 0.125f, 0.08333f, 0.0625f};

/* Chorus container: its four knobs are not on the panel, and only the first program has values for them.
 * The other programs hold zeros, so there the delay is 0 samples and the "Chorus" slider just mixes the
 * signal with itself (up to +3 dB at the middle). Checked against the DLL running under Wine. */
#define CH_RATE_V (-9.069625f)   /* 1 V/oct: 440 * 2^(v-5) = 0.0256 Hz */
#define CH_DEPTH 0.4191325f      /* Level Adj gain, 10 V = 1 */
#define CH_MIN 0.115f            /* minimum delay, as a fraction of 0.06 s */
#define CH_PHASE 0.0162715f      /* the right channel's LFO runs this many cycles behind (Phase Mod 0.32543 V * PM Depth 5 V) */
#define CH_TIME 0.06f

enum { SEG_IDLE, SEG_ATTACK, SEG_DECAY, SEG_SUSTAIN, SEG_RELEASE };
typedef struct { int seg; float lvl; } env_t;

typedef struct {
    int active, note, gate, sustained;
    unsigned age;
    float vel;
    float pitch, pitch_target, pitch_inc;   /* volts */
    int glide_left;
    float phase, inc;
    env_t amp, nz, vib;
    float fol;                               /* peak follower */
    float vibg;
    double b0, b1, b2, a1, a2, x1, x2, y1, y2;
    float fpitch;                            /* filter pitch the coefficients were made for */
    int tail;
} voice_t;

typedef struct {
    float p[NP];
    voice_t v[NVOICES];
    unsigned age, rng;
    int tick;
    /* note handling */
    uint8_t held[16], held_vel[16], down[128];
    int nheld, pedal;
    float last_pitch;
    int have_last;
    float bend, bend_target, bend_inc;
    double bpm;
    float lfo_phase, lfo;
    /* derived from the parameters */
    float rate_a, rate_d, rate_r, sus;       /* main ADSR, level per sample */
    float vrate_a;
    float nz_a, nz_d, nz_r, fix_d, fix_r;
    float fol_ca, fol_cd;
    float g_noise, g_osc, g_wet, g_dry, g_cho, g_chodry, g_out;
    float q, comp, envmod, cutoff_v, vib_amt;
    float porta_time;
    int poly;
    int dirty;                               /* filter settings changed: remake every voice's coefficients */
    int meow, meow_wait;                     /* the cat's frame (0 = mouth shut), refreshed about 40 times a second */
    /* chorus */
    float dl[DELAY_LEN];
    int dpos;
    float ch_phase, ch_delay[2];
    float ch_depth, ch_min;                  /* this program's hidden chorus knobs */
    float vca[VCA_N + 2];
} synth_t;

/* ---- SynthEdit module maths ------------------------------------------------------------------------ */

/* ADSR rate pins: 0 V = 9.8 ms, +1 V doubles it, 10 V = 10 s, for a full 0..10 V sweep (segments are linear). */
static float rate_per_sample(float volts) { return 1.0f / (SR * powf(2.0f, volts - 6.6666667f)); }

/* VCA "Exponential" response curve (control 0..1 = 0..10 V) */
static float vca_curve(float v) {
    if (v <= 0) return 0;
    float g = 1.0f - (1.0f - expf(-3.0f * (1.0f - v))) / (1.0f - expf(-3.0f));
    if (v < 0.001f) g *= v * 1000.0f;
    return g;
}

static float vca_gain(const synth_t *s, float v) {
    if (v <= 0) return 0;
    if (v >= 1) return v > 1 ? vca_curve(v) : 1.0f;
    float x = v * VCA_N;
    int i = (int)x;
    return s->vca[i] + (s->vca[i + 1] - s->vca[i]) * (x - i);
}

/* DH_MultiFilter2 "Res(v)" -> Q, and its gain compensation for one filter stage */
static float reso_to_q(float volts) {
    float r = volts * 0.1f;
    if (r < 0) r = 0;
    if (r > 1) r = 1;
    return expf(0.05f * expf(4.5f * r)) - 0.6f;
}

static float gain_comp(float q) {
    static const float row[9] = {0.8f, 0.85f, 0.85f, 0.85f, 0.85f, 0.853f, 0.89f, 0.872f, 1.12f};
    float x = logf(q), f;
    if (x <= 0) f = row[0];
    else if (x >= 4) f = row[8];
    else {
        int k = (int)(2 * x);
        f = row[k] + (row[k + 1] - row[k]) * (2 * x - k);
    }
    return f * expf(((-0.0041f * x - 0.0144f) * x - 0.2461f) * x + 0.2759f);
}

/* X-Mix "Equal Power": mix 0..1 (-5..+5 V) -> gains of input A and input B */
static void xmix(float m, float *a, float *b) {
    if (m < 0) m = 0;
    if (m > 1) m = 1;
    *a = sinf(m * PI_F * 0.5f);
    *b = sinf((1 - m) * PI_F * 0.5f);
}

static void recalc(synth_t *s) {
    const float *p = s->p;
    s->rate_a = rate_per_sample(p[P_M]);
    s->rate_d = rate_per_sample(p[P_O]);
    s->rate_r = rate_per_sample(p[P_W]);
    s->sus = p[P_E] * 0.1f;
    s->vrate_a = rate_per_sample(p[P_VIB_ATK]);
    s->nz_a = rate_per_sample(0);
    s->fix_d = s->nz_d = rate_per_sample(5);
    s->fix_r = s->nz_r = rate_per_sample(4);
    /* Peak Follower: coefficient = exp(-100 / (pin * SR)) with the pin at 10 V = 1, floor 0.001 */
    float a = p[P_FOL_ATK] * 0.1f, d = p[P_FOL_DEC] * 0.1f;
    s->fol_ca = expf(-100.0f / ((a < 0.001f ? 0.001f : a) * SR));
    s->fol_cd = expf(-100.0f / ((d < 0.001f ? 0.001f : d) * SR));
    xmix(p[P_NOISE] * 0.001f, &s->g_noise, &s->g_osc);        /* 0..100 % = mix -5..-4 V */
    xmix(p[P_FMIX] * 0.01f, &s->g_wet, &s->g_dry);
    xmix(p[P_CHORUS] * 0.01f, &s->g_cho, &s->g_chodry);
    s->g_out = vca_curve(p[P_GAIN] * 0.1f) * OUT_TRIM;
    s->q = reso_to_q(p[P_RESO]);
    s->comp = (int)p[P_FTYPE] <= 2 ? gain_comp(s->q) : 1.0f;
    s->envmod = p[P_ENVMOD] * 0.1f;
    s->cutoff_v = p[P_CUTOFF];
    s->vib_amt = p[P_VIB_AMT] * 0.1f;
    /* Midi to CV portamento: 2^(V - 8.667) seconds, the slider runs 4..10 V */
    s->porta_time = powf(2.0f, 4.0f + 0.06f * p[P_PORTA] - 8.6666667f);
    s->dirty = 1;
}

static void all_off(synth_t *s) {
    for (int i = 0; i < NVOICES; i++) {
        voice_t *v = &s->v[i];
        if (v->gate) { v->gate = 0; v->amp.seg = v->nz.seg = v->vib.seg = SEG_RELEASE; }
        v->sustained = 0;
    }
    s->nheld = 0;
    memset(s->down, 0, sizeof s->down);
}

static void load_preset(synth_t *s, int n) {
    if (n < 0 || n > 4) return;
    float *p = s->p;
    p[P_M] = PRESETS[n].m; p[P_E] = PRESETS[n].e; p[P_O] = PRESETS[n].o; p[P_W] = PRESETS[n].w;
    p[P_VIB_AMT] = PRESETS[n].vib_amt; p[P_VIB_ATK] = PRESETS[n].vib_atk; p[P_VIB_SPEED] = (float)PRESETS[n].speed;
    p[P_NOISE] = PRESETS[n].noise; p[P_CHORUS] = PRESETS[n].chorus;
    if ((int)p[P_POLY] != PRESETS[n].poly) all_off(s);
    p[P_POLY] = (float)PRESETS[n].poly;
    s->ch_depth = n == 0 ? CH_DEPTH : 0;
    s->ch_min = n == 0 ? CH_MIN : 0;
}

/* ---- filter ---------------------------------------------------------------------------------------- */

/* DH_MultiFilter2 in Pitch/Res mode: pitch -2..12 V -> Hz (5 V = 440), capped at 0.99 * Nyquist, then the
 * usual biquad set for the filter type. */
static void set_filter(const synth_t *s, voice_t *v, float pitch_v) {
    if (pitch_v < -2) pitch_v = -2;
    if (pitch_v > 12) pitch_v = 12;
    float f = 440.0f * exp2f(pitch_v - 5.0f);
    if (f > 0.99f * SR * 0.5f) f = 0.99f * SR * 0.5f;
    if (f < 1) f = 1;
    float w = 2.0f * PI_F * f / SR, sn = sinf(w), cs = cosf(w);
    double alpha = sn / (2.0 * s->q), inv = 1.0 / (1.0 + alpha), b0, b1, b2;
    switch ((int)s->p[P_FTYPE]) {
    default: b1 = 1.0 - cs; b0 = b2 = b1 * 0.5; break;                 /* LP */
    case 1: b1 = -1.0 - cs; b0 = b2 = b1 * -0.5; break;               /* HP */
    case 2: b1 = 0; b0 = sn * 0.5; b2 = -b0; break;                   /* BP1: peak gain = Q */
    case 3: b1 = 0; b0 = alpha; b2 = -alpha; break;                   /* BP2: peak gain = 1 */
    case 4: b0 = b2 = 1; b1 = -2.0 * cs; break;                       /* Notch */
    }
    v->b0 = b0 * inv; v->b1 = b1 * inv; v->b2 = b2 * inv;
    v->a1 = -2.0 * cs * inv; v->a2 = (1.0 - alpha) * inv;
    v->fpitch = pitch_v;
}

/* ---- envelopes ------------------------------------------------------------------------------------- */

static inline void env_step(env_t *e, float ra, float rd, float sus, float rr) {
    switch (e->seg) {
    case SEG_ATTACK:
        e->lvl += ra;
        if (e->lvl >= 1.0f) { e->lvl = 1.0f; e->seg = SEG_DECAY; }
        break;
    case SEG_DECAY:
        if (e->lvl > sus) { e->lvl -= rd; if (e->lvl <= sus) { e->lvl = sus; e->seg = SEG_SUSTAIN; } }
        else { e->lvl += rd; if (e->lvl >= sus) { e->lvl = sus; e->seg = SEG_SUSTAIN; } }
        break;
    case SEG_SUSTAIN:
        e->lvl = sus;
        break;
    case SEG_RELEASE:
        e->lvl -= rr;
        if (e->lvl <= 0) { e->lvl = 0; e->seg = SEG_IDLE; }
        break;
    default: break;
    }
}

/* ---- notes ----------------------------------------------------------------------------------------- */

static float note_volts(int note) { return (note - 69) / 12.0f + 5.0f; }

/* Portamento works as in the original: a note played while another key is down glides from the last note's
 * pitch; a note played with no key down starts on pitch. */
static void glide_to(synth_t *s, voice_t *v, float target, int legato) {
    v->pitch_target = target;
    int steps = legato && s->have_last ? (int)(s->porta_time * SR + 0.5f) : 0;
    if (!v->active) v->pitch = s->have_last ? s->last_pitch : target;   /* a fresh voice starts where the last note was */
    if (steps < 1 || fabsf(target - v->pitch) < 1e-6f) { v->pitch = target; v->glide_left = 0; }
    else { v->pitch_inc = (target - v->pitch) / steps; v->glide_left = steps; }
    s->last_pitch = target;
    s->have_last = 1;
}

static void trigger(synth_t *s, voice_t *v, int note, int vel, int legato) {
    glide_to(s, v, note_volts(note), legato);
    if (!v->active) {
        v->amp.lvl = v->nz.lvl = v->vib.lvl = 0;
        v->fol = 0;
        v->x1 = v->x2 = v->y1 = v->y2 = 0;
        v->fpitch = -100;
    }
    v->active = 1; v->note = note; v->gate = 1; v->sustained = 0;
    v->vel = vel / 127.0f;
    v->age = ++s->age;
    v->phase = 0;                                    /* the gate is wired to the oscillator's Sync input */
    v->amp.seg = v->nz.seg = v->vib.seg = SEG_ATTACK;
    v->tail = 0;
}

static void release(voice_t *v) {
    v->gate = 0; v->sustained = 0;
    if (v->amp.seg != SEG_IDLE) v->amp.seg = SEG_RELEASE;
    if (v->nz.seg != SEG_IDLE) v->nz.seg = SEG_RELEASE;
    if (v->vib.seg != SEG_IDLE) v->vib.seg = SEG_RELEASE;
}

static int keys_down(const synth_t *s) {
    int n = 0;
    for (int i = 0; i < 128; i++) n += s->down[i];
    return n;
}

static void note_on(synth_t *s, int note, int vel) {
    int legato = keys_down(s) > 0;
    s->down[note] = 1;
    if (!s->poly) {
        /* Mono Mode, last-note priority, Retrigger on */
        for (int i = 0; i < s->nheld; i++)
            if (s->held[i] == note) { memmove(&s->held[i], &s->held[i + 1], s->nheld - i - 1); memmove(&s->held_vel[i], &s->held_vel[i + 1], s->nheld - i - 1); s->nheld--; break; }
        if (s->nheld == 16) { memmove(s->held, s->held + 1, 15); memmove(s->held_vel, s->held_vel + 1, 15); s->nheld = 15; }
        s->held[s->nheld] = (uint8_t)note; s->held_vel[s->nheld++] = (uint8_t)vel;
        for (int i = 1; i < NVOICES; i++) if (s->v[i].gate) release(&s->v[i]);
        trigger(s, &s->v[0], note, vel, legato);
        return;
    }
    voice_t *pick = NULL;
    for (int i = 0; i < NVOICES && !pick; i++) if (!s->v[i].active) pick = &s->v[i];
    if (!pick) {
        for (int i = 0; i < NVOICES; i++)             /* oldest released voice, else the oldest voice */
            if (!s->v[i].gate && (!pick || s->v[i].age < pick->age)) pick = &s->v[i];
        if (!pick) for (int i = 0; i < NVOICES; i++) if (!pick || s->v[i].age < pick->age) pick = &s->v[i];
    }
    if (pick->active) pick->active = 0;               /* a stolen voice starts over */
    trigger(s, pick, note, vel, legato);
}

static void note_off(synth_t *s, int note) {
    s->down[note] = 0;
    if (!s->poly) {
        int was_top = s->nheld > 0 && s->held[s->nheld - 1] == note;
        for (int i = 0; i < s->nheld; i++)
            if (s->held[i] == note) { memmove(&s->held[i], &s->held[i + 1], s->nheld - i - 1); memmove(&s->held_vel[i], &s->held_vel[i + 1], s->nheld - i - 1); s->nheld--; break; }
        voice_t *v = &s->v[0];
        if (!v->gate || v->note != note || !was_top) return;
        if (s->nheld > 0) trigger(s, v, s->held[s->nheld - 1], s->held_vel[s->nheld - 1], 1);   /* back to the key still held */
        else if (s->pedal) v->sustained = 1;
        else release(v);
        return;
    }
    for (int i = 0; i < NVOICES; i++) {
        voice_t *v = &s->v[i];
        if (v->gate && v->note == note && !v->sustained) { if (s->pedal) v->sustained = 1; else release(v); }
    }
}

static void midi(void *inst, const uint8_t *m, int len) {
    synth_t *s = inst;
    if (len < 2) return;
    int st = m[0] & 0xf0, d1 = m[1] & 0x7f, d2 = len > 2 ? m[2] & 0x7f : 0;
    switch (st) {
    case 0x90: if (d2) note_on(s, d1, d2); else note_off(s, d1); break;   /* velocity 0 = note off */
    case 0x80: note_off(s, d1); break;
    case 0xb0:
        if (d1 == 64) {
            s->pedal = d2 >= 64;
            if (!s->pedal) for (int i = 0; i < NVOICES; i++) if (s->v[i].sustained) release(&s->v[i]);
        } else if (d1 == 120 || d1 == 123) all_off(s);
        break;
    case 0xe0:
        /* Bender: +-Bend Range semitones, glided over 1/60 s like the original */
        s->bend_target = (((d2 << 7) | d1) - 8192) / 8192.0f * s->p[P_BEND] / 12.0f;
        s->bend_inc = (s->bend_target - s->bend) / (SR / 60.0f);
        break;
    default: break;
    }
}

/* ---- parameters ------------------------------------------------------------------------------------ */

static int find_param(const char *key) {
    for (int i = 0; i < NP; i++) if (!strcmp(key, PD[i].key)) return i;
    return -1;
}

static void store(synth_t *s, int i, float v) {
    if (v < PD[i].min) v = PD[i].min;
    if (v > PD[i].max) v = PD[i].max;
    if (PD[i].integer) v = roundf(v);
    s->p[i] = v;
}

static int get_state(synth_t *s, char *buf, int len) {
    int n = snprintf(buf, len, "MEOW1");
    for (int i = 0; i < NP && n < len; i++) n += snprintf(buf + n, len - n, " %s=%g", PD[i].key, (double)s->p[i]);
    if (n < len) n += snprintf(buf + n, len - n, " ch_depth=%g ch_min=%g", (double)s->ch_depth, (double)s->ch_min);
    return n < len ? n : 0;
}

static void set_state(synth_t *s, const char *str) {
    if (strncmp(str, "MEOW1", 5)) return;
    const char *q = str + 5;
    char key[32];
    while (*q) {
        while (*q == ' ') q++;
        const char *eq = strchr(q, '=');
        if (!eq || eq - q >= (int)sizeof key) break;
        memcpy(key, q, eq - q); key[eq - q] = 0;
        int i = find_param(key);
        if (i >= 0) store(s, i, (float)atof(eq + 1));  /* the saved preset index is only a label here */
        else if (!strcmp(key, "ch_depth")) s->ch_depth = (float)atof(eq + 1);
        else if (!strcmp(key, "ch_min")) s->ch_min = (float)atof(eq + 1);
        q = strchr(eq, ' ');
        if (!q) break;
    }
    if ((int)s->p[P_POLY] != s->poly) all_off(s);
    s->poly = (int)s->p[P_POLY];
    recalc(s);
}

static void set_param(void *inst, const char *key, const char *val) {
    synth_t *s = inst;
    if (!strcmp(key, "lfo_bpm")) { double b = atof(val); if (b > 1) s->bpm = b; return; }
    if (!strcmp(key, "state")) { set_state(s, val); return; }
    int i = find_param(key);
    if (i < 0) return;
    float old = s->p[i];
    store(s, i, (float)atof(val));
    if (i == P_PRESET && s->p[i] != old) load_preset(s, (int)s->p[i]);
    if ((int)s->p[P_POLY] != s->poly) { all_off(s); s->poly = (int)s->p[P_POLY]; }
    recalc(s);
}

static int get_param(void *inst, const char *key, char *buf, int len) {
    synth_t *s = inst;
    if (!strcmp(key, "state")) return get_state(s, buf, len);
    if (!strcmp(key, "meow")) return snprintf(buf, len, "%d", s->meow);
    int i = find_param(key);
    if (i < 0) return 0;
    return PD[i].integer ? snprintf(buf, len, "%d", (int)s->p[i]) : snprintf(buf, len, "%g", (double)s->p[i]);
}

/* ---- audio ----------------------------------------------------------------------------------------- */

static inline float frand(synth_t *s) {              /* white noise, +-0.5 (+-5 V) */
    s->rng = s->rng * 1664525u + 1013904223u;
    return (float)(int32_t)s->rng * (0.5f / 2147483648.0f);
}

static inline float blep(float t, float dt) {
    if (t < dt) { t /= dt; return t + t - t * t - 1.0f; }
    if (t > 1.0f - dt) { t = (t - 1.0f) / dt; return t * t + t + t + 1.0f; }
    return 0;
}

static void render(void *inst, int16_t *out, int frames) {
    synth_t *s = inst;
    const float ch_inc = 440.0f * exp2f(CH_RATE_V - 5.0f) / SR;
    const float lfo_inc = (float)(s->bpm / (60.0 * DIV_BEATS[(int)s->p[P_VIB_SPEED]])) / SR;
    const int noisy = s->g_noise > 0;
    for (int n = 0; n < frames; n++) {
        const int ctrl = (s->tick++ & (CTRL - 1)) == 0;
        if (ctrl) {
            s->lfo_phase += lfo_inc * CTRL;
            s->lfo_phase -= floorf(s->lfo_phase);
            s->lfo = 0.5f * sinf(2.0f * PI_F * s->lfo_phase);          /* +-5 V sine */
        }
        if (s->bend != s->bend_target) {
            s->bend += s->bend_inc;
            if ((s->bend_inc > 0) == (s->bend >= s->bend_target)) s->bend = s->bend_target;
        }
        float mix = 0;
        for (int i = 0; i < NVOICES; i++) {
            voice_t *v = &s->v[i];
            if (!v->active) continue;
            if (v->glide_left > 0) { v->pitch += v->pitch_inc; if (--v->glide_left == 0) v->pitch = v->pitch_target; }
            env_step(&v->amp, s->rate_a, s->rate_d, s->sus, s->rate_r);
            env_step(&v->vib, s->vrate_a, s->fix_d, 0.7f, s->fix_r);
            if (ctrl) {
                v->vibg = vca_gain(s, v->vib.lvl * s->vib_amt);
                float pv = v->pitch + s->bend + 10.0f * s->lfo * v->vibg;
                float inc = 440.0f * exp2f(pv - 5.0f) / SR;
                v->inc = inc > 0.45f ? 0.45f : inc;
                float fp = s->cutoff_v + 10.0f * v->fol * s->envmod;
                if (s->dirty || fabsf(fp - v->fpitch) > 1e-4f) set_filter(s, v, fp);
            }
            /* ramp oscillator, +-5 V */
            float osc = v->phase - 0.5f - 0.5f * blep(v->phase, v->inc);
            v->phase += v->inc;
            if (v->phase >= 1.0f) v->phase -= 1.0f;
            float x = osc * vca_gain(s, v->amp.lvl * v->vel) * s->g_osc;
            if (noisy) {
                env_step(&v->nz, s->nz_a, s->nz_d, 0.7f, s->nz_r);
                x += frand(s) * vca_gain(s, v->nz.lvl) * s->g_noise;
            } else if (v->nz.seg != SEG_IDLE) env_step(&v->nz, s->nz_a, s->nz_d, 0.7f, s->nz_r);
            /* Peak Follower on both filter inputs (the same signal twice) */
            float a = fabsf(x + x);
            v->fol = a + (v->fol - a) * (a > v->fol ? s->fol_ca : s->fol_cd);
            double y = v->b0 * x + v->b1 * v->x1 + v->b2 * v->x2 - v->a1 * v->y1 - v->a2 * v->y2 + 1e-18;
            v->x2 = v->x1; v->x1 = x; v->y2 = v->y1; v->y1 = y;
            float o = (float)y * s->comp * s->g_wet + x * s->g_dry;
            mix += o;
            if (v->amp.seg == SEG_IDLE && v->nz.seg == SEG_IDLE) {
                /* both VCAs are shut: let the filter ring out, then free the voice */
                if (++v->tail > 2048 || (fabsf(o) < 1e-6f && v->fol < 1e-6f)) v->active = 0;
            }
        }
        if (ctrl) s->dirty = 0;
        mix *= s->g_out;
        /* Chorus: one delay line, a tap per channel swept by two slow sines a few degrees apart */
        if (ctrl) {
            for (int c = 0; c < 2; c++) {
                float ph = s->ch_phase - (c ? CH_PHASE : 0);
                s->ch_delay[c] = (s->ch_min + s->ch_depth * (0.5f * sinf(2.0f * PI_F * ph) + 0.5f)) * CH_TIME * SR;
            }
            s->ch_phase += ch_inc * CTRL;
            if (s->ch_phase >= 1.0f) s->ch_phase -= 1.0f;
        }
        s->dl[s->dpos] = mix;
        float outc[2];
        for (int c = 0; c < 2; c++) {
            int di = (int)s->ch_delay[c];
            float fr = s->ch_delay[c] - di;
            float s0 = s->dl[(s->dpos - di) & (DELAY_LEN - 1)], s1 = s->dl[(s->dpos - di - 1) & (DELAY_LEN - 1)];
            float o = (s0 + (s1 - s0) * fr) * s->g_cho + mix * s->g_chodry;
            float ab = fabsf(o);                                         /* soft knee into int16 */
            if (ab > 0.75f) o = copysignf(0.75f + 0.24f * tanhf((ab - 0.75f) / 0.24f), o);
            outc[c] = o;
        }
        s->dpos = (s->dpos + 1) & (DELAY_LEN - 1);
        out[2 * n] = (int16_t)lrintf(outc[0] * 32767.0f);
        out[2 * n + 1] = (int16_t)lrintf(outc[1] * 32767.0f);
    }
    /* The original animates its cat from the amp envelope: whole volts of ADSR output (0..10), sampled at
     * 40 Hz, pick one of the 12 frames. */
    if ((s->meow_wait += frames) >= (int)(SR / 40)) {
        float top = 0;
        for (int i = 0; i < NVOICES; i++)
            if (s->v[i].active && s->v[i].amp.lvl * s->v[i].vel > top) top = s->v[i].amp.lvl * s->v[i].vel;
        s->meow = (int)(top * 10.0f) > 11 ? 11 : (int)(top * 10.0f);
        s->meow_wait = 0;
    }
}

static void *create(const char *data_dir) {
    (void)data_dir;
    synth_t *s = calloc(1, sizeof *s);
    if (!s) return NULL;
    for (int i = 0; i < NP; i++) s->p[i] = PD[i].def;
    for (int i = 0; i <= VCA_N + 1; i++) s->vca[i] = vca_curve((float)i / VCA_N);
    s->rng = 0x12345678u;
    s->bpm = 120.0;
    load_preset(s, 0);
    recalc(s);
    return s;
}

static void destroy(void *inst) { free(inst); }

static const mpc_engine_t ENGINE = { create, destroy, midi, set_param, get_param, render, NULL };
const mpc_engine_t *mpc_engine(void) { return &ENGINE; }
