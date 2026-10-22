/* The five cats as MPC presets: prints "<cat index>\t<state>" for each, the state being what the engine itself saves
 * (the VST chunk) on a fresh instance with that cat picked, so a preset holds exactly what picking the cat on the page
 * gives. build.sh compiles it with the engine and runs it; tools/meow_art.py presets wraps each state in an .xpl. */
#include <stdio.h>
#include "engine.h"

int main(void) {
    const mpc_engine_t *api = mpc_engine();
    char v[4], st[1024];
    for (int c = 0; c < 5; c++) {
        void *s = api->create(NULL);
        if (!s) return 1;
        snprintf(v, sizeof v, "%d", c);
        api->set_param(s, "preset", v);
        if (api->get_param(s, "state", st, sizeof st) <= 0) return 1;
        printf("%d\t%s\n", c, st);
        api->destroy(s);
    }
    return 0;
}
