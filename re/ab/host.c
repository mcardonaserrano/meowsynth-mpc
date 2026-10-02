/* Minimal freestanding VST2 host for Win32: runs a command file against a plugin DLL. */
typedef unsigned int u32; typedef int i32; typedef unsigned char u8;
#define IMP __declspec(dllimport)
#define SC __stdcall
IMP void *SC LoadLibraryA(const char *); IMP void *SC GetProcAddress(void *, const char *);
IMP void *SC CreateFileA(const char *, u32, u32, void *, u32, u32, void *);
IMP i32 SC WriteFile(void *, const void *, u32, u32 *, void *); IMP i32 SC ReadFile(void *, void *, u32, u32 *, void *);
IMP i32 SC CloseHandle(void *); IMP void SC ExitProcess(u32); IMP u32 SC GetLastError(void);
int _fltused = 0x9875;
void *memset(void *d, int c, u32 n) { u8 *p = d; while (n--) *p++ = (u8)c; return d; }
void *memcpy(void *d, const void *s, u32 n) { u8 *p = d; const u8 *q = s; while (n--) *p++ = *q++; return d; }

typedef struct AEffect AEffect;
typedef i32 (__cdecl *amcb)(AEffect *, i32, i32, i32, void *, float);
struct AEffect { i32 magic; i32 (__cdecl *dispatcher)(AEffect *, i32, i32, i32, void *, float);
  void (__cdecl *process)(AEffect *, float **, float **, i32); void (__cdecl *setParameter)(AEffect *, i32, float);
  float (__cdecl *getParameter)(AEffect *, i32); i32 numPrograms, numParams, numInputs, numOutputs, flags, r1, r2,
  initialDelay, rq, oq; float ioRatio; void *object, *user; i32 uniqueID, version;
  void (__cdecl *processReplacing)(AEffect *, float **, float **, i32); void *pdr; char future[56]; };
typedef struct { double samplePos, sampleRate, nanoSeconds, ppqPos, tempo, barStartPos, cycleStartPos, cycleEndPos;
  i32 timeSigNumerator, timeSigDenominator, smpteOffset, smpteFrameRate, samplesToNextClock, flags; } TimeInfo;
typedef struct { i32 type, byteSize, deltaFrames, flags, noteLength, noteOffset; u8 midi[4]; char detune, nov, r1, r2; } MidiEv;
typedef struct { i32 numEvents; i32 reserved; void *events[2]; } Events;
typedef struct { u32 op; i32 a, b; float c; } Cmd;

static TimeInfo ti; static void *logh; static i32 opcount[64];
static void wr(void *h, const void *p, u32 n) { u32 k; WriteFile(h, p, n, &k, 0); }
static u32 slen(const char *s) { u32 n = 0; while (s[n]) n++; return n; }
static void ws(void *h, const char *s) { wr(h, s, slen(s)); }
static void wi(void *h, i32 v) { char b[16]; int n = 15; u32 u = v < 0 ? (u32)-v : (u32)v; b[15] = 0;
  do { b[--n] = (char)('0' + u % 10); u /= 10; } while (u); if (v < 0) b[--n] = '-'; ws(h, b + n); }
static i32 __cdecl master(AEffect *e, i32 op, i32 idx, i32 val, void *ptr, float opt) {
  if (op >= 0 && op < 64) opcount[op]++;
  switch (op) {
  case 1: return 2400;                 /* audioMasterVersion */
  case 7: return (i32)&ti;             /* audioMasterGetTime */
  case 16: return 44100; case 17: return 128;
  case 23: return 2;                   /* process level: realtime */
  default: return 0; }
}
static float L[128], R[128], Z1[128], Z2[128];
static u8 cmdbuf[1 << 20];

void __stdcall entry(void) {
  u32 n;
  logh = CreateFileA("host.log", 0x40000000, 0, 0, 2, 0x80, 0);
  void *out = CreateFileA("out.raw", 0x40000000, 0, 0, 2, 0x80, 0);
  void *ch = CreateFileA("cmd.bin", 0x80000000, 1, 0, 3, 0x80, 0);
  ReadFile(ch, cmdbuf, sizeof cmdbuf, &n, 0); CloseHandle(ch);
  ti.sampleRate = 44100; ti.tempo = 120; ti.timeSigNumerator = 4; ti.timeSigDenominator = 4; ti.flags = (1 << 10) | 2 | (1 << 9) | (1 << 13);
  void *dll = LoadLibraryA("MeowSynth.dll");
  ws(logh, "dll "); wi(logh, dll != 0); ws(logh, " err "); wi(logh, (i32)GetLastError()); ws(logh, "\r\n");
  if (!dll) ExitProcess(2);
  AEffect *(__cdecl *mainf)(amcb) = (AEffect *(__cdecl *)(amcb))GetProcAddress(dll, "main");
  if (!mainf) { ws(logh, "no main\r\n"); ExitProcess(3); }
  AEffect *e = mainf(master);
  ws(logh, "effect "); wi(logh, e != 0); ws(logh, "\r\n");
  if (!e || e->magic != 0x56737450) ExitProcess(4);
  ws(logh, "programs "); wi(logh, e->numPrograms); ws(logh, " params "); wi(logh, e->numParams); ws(logh, " in "); wi(logh, e->numInputs);
  ws(logh, " out "); wi(logh, e->numOutputs); ws(logh, " flags "); wi(logh, e->flags); ws(logh, "\r\n");
  e->dispatcher(e, 0, 0, 0, 0, 0);
  e->dispatcher(e, 10, 0, 0, 0, 44100.0f);
  e->dispatcher(e, 11, 0, 128, 0, 0);
  e->dispatcher(e, 12, 0, 1, 0, 0);
  ws(logh, "opened\r\n");
  Cmd *c = (Cmd *)cmdbuf; u32 nc = n / sizeof(Cmd);
  float *ins[2] = {Z1, Z2}, *outs[2] = {L, R};
  for (u32 k = 0; k < nc; k++, c++) {
    if (c->op == 1) e->dispatcher(e, 2, 0, c->a, 0, 0);
    else if (c->op == 2) e->setParameter(e, c->a, c->c);
    else if (c->op == 3) {
      /* consecutive MIDI commands go to the plugin as one event list, as a host delivers a block's events */
      static MidiEv m[16]; static struct { i32 numEvents; i32 reserved; void *events[16]; } ev;
      i32 k2 = 0;
      while (k < nc && c->op == 3 && k2 < 16) {
        m[k2].type = 1; m[k2].byteSize = sizeof(MidiEv); m[k2].deltaFrames = 0; m[k2].flags = 0;
        m[k2].midi[0] = (u8)c->a; m[k2].midi[1] = (u8)(c->a >> 8); m[k2].midi[2] = (u8)(c->a >> 16); m[k2].midi[3] = 0;
        ev.events[k2] = &m[k2]; k2++; k++; c++;
      }
      k--; c--;
      ev.numEvents = k2;
      e->dispatcher(e, 25, 0, 0, &ev, 0);
    } else if (c->op == 4) {
      for (i32 b = 0; b < c->a; b++) {
        memset(L, 0, sizeof L); memset(R, 0, sizeof R);
        if (e->flags & 16) e->processReplacing(e, ins, outs, 128); else e->process(e, ins, outs, 128);
        ti.samplePos += 128; ti.ppqPos += 128.0 / 44100.0 * ti.tempo / 60.0;
        wr(out, L, sizeof L); wr(out, R, sizeof R);
      }
    } else if (c->op == 5) {
      void *ph = CreateFileA("params.txt", 0x40000000, 0, 0, 2, 0x80, 0);
      static char s[256];
      i32 cur = e->dispatcher(e, 3, 0, 0, 0, 0);
      for (i32 p = 0; p < e->numPrograms && p < 8; p++) {
        memset(s, 0, sizeof s); e->dispatcher(e, 2, 0, p, 0, 0); e->dispatcher(e, 5, 0, 0, s, 0);
        ws(ph, "program "); wi(ph, p); ws(ph, " '"); ws(ph, s); ws(ph, "'\r\n");
        for (i32 i = 0; i < e->numParams; i++) {
          wi(ph, i); ws(ph, " |");
          memset(s, 0, sizeof s); e->dispatcher(e, 8, i, 0, s, 0); ws(ph, s); ws(ph, "| ");
          memset(s, 0, sizeof s); e->dispatcher(e, 7, i, 0, s, 0); ws(ph, s); ws(ph, " ");
          memset(s, 0, sizeof s); e->dispatcher(e, 6, i, 0, s, 0); ws(ph, s); ws(ph, " = ");
          wi(ph, (i32)(e->getParameter(e, i) * 1000000.0f)); ws(ph, "\r\n");
        }
      }
      e->dispatcher(e, 2, 0, cur, 0, 0);
      CloseHandle(ph);
    } else if (c->op == 6) ti.tempo = c->c;
  }
  ws(logh, "done; master ops:");
  for (i32 i = 0; i < 64; i++) if (opcount[i]) { ws(logh, " "); wi(logh, i); ws(logh, "x"); wi(logh, opcount[i]); }
  ws(logh, "\r\n");
  CloseHandle(out); CloseHandle(logh);
  ExitProcess(0);
}
