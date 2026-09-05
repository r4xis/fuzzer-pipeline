#include <stdint.h>
#include <stddef.h>
#include <gme/gme.h>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4) return 0;

    Music_Emu *emu = nullptr;
    const int sample_rate = 44100;

    gme_err_t err = gme_open_data(data, size, &emu, sample_rate);
    if (err || !emu) return 0;

    int track_count = gme_track_count(emu);
    if (track_count <= 0) {
        gme_delete(emu);
        return 0;
    }

    // ilk 3 track'i test et
    int tracks_to_test = track_count < 3 ? track_count : 3;

    for (int t = 0; t < tracks_to_test; t++) {
        err = gme_start_track(emu, t);
        if (err) continue;

        short buf[2048];
        for (int i = 0; i < 10; i++) {
            if (gme_track_ended(emu)) break;
            gme_play(emu, 2048, buf);
        }
    }

    gme_delete(emu);
    return 0;
}
