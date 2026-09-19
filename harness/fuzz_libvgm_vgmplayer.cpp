#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>	// __AFL_FUZZ_TESTCASE_LEN expands to a bare read(0, ...) call

#include "player/vgmplayer.hpp"
#include "utils/DataLoader.h"
#include "utils/MemoryLoader.h"

#ifdef __AFL_FUZZ_TESTCASE_LEN
__AFL_FUZZ_INIT();
#endif

// Bounds the number of Render() calls per input so a crafted loop point or a
// long DAC stream can't hang the fuzzer: MAX_RENDER_ITERS * 1024 samples is
// ~4.6s of audio at 44100Hz, which is enough to exercise command parsing and
// device emulation without ever spinning unbounded (see VGMPlayer::Render()/
// ParseFile(), which otherwise only stop at PLAYSTATE_END or a loop).
static const int MAX_RENDER_ITERS = 200;

static void run_one(const uint8_t *data, size_t size)
{
    if (size < 0x40)
        return;

    DATA_LOADER *loader = MemoryLoader_Init(data, (UINT32)size);
    if (loader == NULL)
        return;
    if (DataLoader_Load(loader) != 0x00)
    {
        DataLoader_Deinit(loader);
        return;
    }

    VGMPlayer *player = new VGMPlayer();
    if (player->LoadFile(loader) == 0x00)
    {
        // _outSmplRate defaults to 0 (PlayerBase ctor); Start() -> InitDevices()
        // divides by it (e.g. sn76496_freq_limiter), so this must be set first.
        player->SetSampleRate(44100);
        player->Start();

        WAVE_32BS buf[1024];
        for (int i = 0; i < MAX_RENDER_ITERS; i++)
        {
            player->Render(1024, buf);
            if (player->GetState() & PLAYSTATE_END)
                break;
            if (player->GetCurLoop() >= 1)	// VGMPlayer has no SetLoopCount() of
                break;			// its own (that's PlayerA-only); cap at 1 loop by hand
        }
    }
    delete player;	// ~VGMPlayer() calls Stop() + UnloadFile(); it does not own the loader
    DataLoader_Deinit(loader);
}

int main(int argc, char **argv)
{
    // Runtime dispatch, not a compile-time #ifdef: triage/run_triage.sh runs
    // CASR as `casr-afl ... -- /fuzzing/harness @@`, which puts the crash
    // file in argv[1] regardless of how the binary was built. An AFL/persistent
    // build must still honor that convention -- if the AFL branch were chosen
    // at compile time (old code: #ifdef __AFL_FUZZ_TESTCASE_LEN picks the
    // persistent loop unconditionally), an AFL-instrumented binary given a
    // file argument would ignore it, read whatever is on stdin instead, see
    // no crash, and CASR would emit no .casrep -- silently dropping the
    // finding before it ever reaches the DB. File mode below runs identically
    // in a plain build and an AFL-instrumented one, and never touches any
    // AFL macro, so `harness <file>` always means "replay this one input".
    if (argc >= 2)
    {
        FILE *f = fopen(argv[1], "rb");
        if (!f)
            return 1;
        fseek(f, 0, SEEK_END);
        long sz = ftell(f);
        fseek(f, 0, SEEK_SET);
        uint8_t *data = (uint8_t*)malloc(sz);
        fread(data, 1, sz, f);
        fclose(f);
        run_one(data, (size_t)sz);
        free(data);
        return 0;
    }

#ifdef __AFL_FUZZ_TESTCASE_LEN
    // No file argument: this is the campaign path. afl-fuzz must be invoked
    // WITHOUT @@ for this target (shared-memory persistent-mode input, not a
    // file argument) -- see docker-compose.yml's `-- harness @@` convention,
    // which does not apply here.
    __AFL_INIT();
    unsigned char *buf = __AFL_FUZZ_TESTCASE_BUF;
    while (__AFL_LOOP(10000))
    {
        int len = __AFL_FUZZ_TESTCASE_LEN;
        run_one(buf, (size_t)len);
    }
    return 0;
#else
    fprintf(stderr, "usage: %s <file>\n", argv[0]);
    return 1;
#endif
}
