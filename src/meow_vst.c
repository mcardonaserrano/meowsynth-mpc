/* MeowSynth's VST2 entry point: the stock wrapper (mpc-vst-plugins wrapper/vst2_wrap.c, compiled in here
 * unchanged) plus the one thing it has no path for -- telling MPC about a value the engine changes by
 * itself (mpc-vst-plugins docs/NOTES.md, "Engine-driven parameter changes never reach the display").
 * The cat on the page is twelve pictures shown by the "meow" parameter (IndexedEnabling); the engine moves
 * that parameter with the amp envelope, and each change is reported with audioMasterAutomate from the
 * audio callback, the way the wrapper already reports its own trigger and popup changes.
 * Build with -DMEOW_ANIMATE=0 for a still cat (the stock wrapper's behaviour). */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <ctype.h>

#ifndef MEOW_ANIMATE
#define MEOW_ANIMATE 1
#endif

/* The stock entry point becomes a plain internal function: renamed, and its export attribute swapped for
 * a harmless one (the build hides everything that is not marked for export). */
#define VSTPluginMain meow_stock_main
#define visibility(x) unused
#include "vst2_wrap.c"
#undef visibility
#undef VSTPluginMain

static int meow_param(void) {
    static int idx = -2;
    if (idx == -2) {
        idx = -1;
        for (int i = 0; i < NPARAMS; i++)
            if (!strcmp(PARAMS[i].key, "meow")) idx = i;
    }
    return idx;
}

/* last_on[] is the wrapper's "value last told to the host, +1" slot; it only uses it for text params */
static void meow_report(AEffect *e) {
    wrap_t *w = e->object;
    int i = meow_param();
    char b[16];
    if (i < 0 || PARAMS[i].nopts < 2 || g_api->get_param(w->dsp, "meow", b, sizeof b) <= 0) return;
    int frame = atoi(b);
    if (w->last_on[i] == frame + 1) return;
    w->last_on[i] = (signed char)(frame + 1);
    w->master(&w->fx, audioMasterAutomate, i, 0, 0, (float)frame / (PARAMS[i].nopts - 1));
}

static void meow_processReplacing(AEffect *e, float **in, float **out, int32_t n) {
    processReplacing(e, in, out, n);
    meow_report(e);
}

static void meow_process(AEffect *e, float **in, float **out, int32_t n) {
    process(e, in, out, n);
    meow_report(e);
}

__attribute__((visibility("default"))) AEffect *VSTPluginMain(audioMasterCallback master) {
    AEffect *e = meow_stock_main(master);
    if (e && MEOW_ANIMATE) {
        e->processReplacing = meow_processReplacing;
        e->process = meow_process;
    }
    return e;
}
