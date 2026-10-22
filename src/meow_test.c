/* The cat check: a note must open the cat's mouth (the engine moves "meow", the entry point tells the host),
 * the mouth must shut again after the note, every preset must sound, and nothing may leave int16 range. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include "params.h"
typedef struct AEffect AEffect;
typedef intptr_t (*cb)(AEffect *, int32_t, int32_t, intptr_t, void *, float);
struct AEffect { int32_t magic; intptr_t (*d)(AEffect *, int32_t, int32_t, intptr_t, void *, float);
    void *p; void (*setP)(AEffect *, int32_t, float); float (*getP)(AEffect *, int32_t);
    int32_t np, npar, ni, no, flags; intptr_t r1, r2; int32_t a, b, c; float io; void *obj, *user; int32_t uid, ver;
    void (*pr)(AEffect *, float **, float **, int32_t); void *pdr; char f[56]; };
typedef struct { int32_t type, byteSize, deltaFrames, flags, noteLength, noteOffset; unsigned char m[4]; char x[4]; } ME;
typedef struct { int32_t n; intptr_t r; void *ev[2]; } EV;
extern AEffect *VSTPluginMain(cb);

static int meow = -1, reports, top_frame, last_frame, fails;
static intptr_t host(AEffect *e, int32_t op, int32_t i, intptr_t v, void *p, float o) {
    static double ti[16];
    (void)e; (void)v; (void)p;
    if (op == 0 && i == meow) { reports++; last_frame = (int)lroundf(o * 11); if (last_frame > top_frame) top_frame = last_frame; }
    if (op == 7) { ti[4] = 120.0; ((int32_t *)&ti[8])[5] = 1 << 10; return (intptr_t)ti; }
    return 0;
}
#define CHECK(c, ...) do { printf("%s ", (c) ? "ok  " : "FAIL"); printf(__VA_ARGS__); printf("\n"); if (!(c)) fails++; } while (0)
static void midi(AEffect *a, int st, int d1, int d2) {
    ME m = {1, sizeof(ME), 0, 0, 0, 0, {(unsigned char)st, (unsigned char)d1, (unsigned char)d2, 0}, {0}};
    EV ev = {1, 0, {&m, 0}};
    a->d(a, 25, 0, 0, &ev, 0);
}
static double run(AEffect *a, int blocks, float *peak) {
    float L[128], R[128], *o[2] = {L, R};
    double e = 0;
    for (int k = 0; k < blocks; k++) {
        a->pr(a, 0, o, 128);
        for (int i = 0; i < 128; i++) {
            e += L[i] * L[i] + R[i] * R[i];
            if (fabsf(L[i]) > *peak) *peak = fabsf(L[i]);
            if (fabsf(R[i]) > *peak) *peak = fabsf(R[i]);
        }
    }
    return sqrt(e / (blocks * 256.0));
}

int main(void) {
    for (int i = 0; i < NPARAMS; i++) if (!strcmp(PARAMS[i].key, "meow")) meow = i;
    CHECK(meow >= 0 && PARAMS[meow].nopts == 12, "\"meow\" is a 12-frame parameter (index %d)", meow);
    AEffect *a = VSTPluginMain(host);
    if (!a) return 1;
    float peak = 0;
    run(a, 20, &peak);
    CHECK(reports <= 1 && top_frame == 0, "silent: the cat's mouth stays shut");
    for (int p = 0; p < 5; p++) {
        a->setP(a, 0, p / 4.0f);
        run(a, 1, &peak);   /* the wrapper applies a host set of parameter 0 (the preset) at the next block */
        reports = top_frame = 0;
        midi(a, 0x90, 60, 127); midi(a, 0x90, 64, 127); midi(a, 0x90, 67, 127);
        double rms = run(a, 344, &peak);                       /* 1 s held */
        midi(a, 0x80, 60, 0); midi(a, 0x80, 64, 0); midi(a, 0x80, 67, 0);
        run(a, 1400, &peak);                                   /* 4 s: the longest release */
        CHECK(rms > 0.005 && top_frame >= 8 && last_frame == 0 && reports >= 4 && reports < 400,
              "%-11s rms %.3f, mouth opens to frame %d and shuts (%d reports)", PARAMS[0].opts[p], rms, top_frame, reports);
    }
    CHECK(peak < 0.999f, "peak %.3f stays inside full scale", peak);
    a->d(a, 1, 0, 0, 0, 0);
    printf("%s\n", fails ? "FAILED" : "PASSED");
    return fails ? 1 : 0;
}
