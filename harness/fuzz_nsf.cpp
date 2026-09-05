#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "gme/gme.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 16) return 0;

    Music_Emu *emu = nullptr;
    const int sample_rate = 44100;

    gme_err_t err = gme_open_data(data, size, &emu, sample_rate);
    if (err || !emu) return 0;

    // Infinite loop engeli — illegal opcode + FDS timeout fix
    gme_set_fade(emu, 1000);

    int track_count = gme_track_count(emu);
    if (track_count <= 0) {
        gme_delete(emu);
        return 0;
    }

    // İlk 3 track'i test et — playlist remap path'i için
    int tracks_to_test = track_count < 3 ? track_count : 3;

    short buf[2048];

    for (int t = 0; t < tracks_to_test; t++) {
        err = gme_start_track(emu, t);
        if (err) continue;

        // 50 iteration — DMC/IRQ frame counter path'lerine ulaşmak için
        // Frame counter case 0→2 fall-through için en az 4 frame lazım
        for (int i = 0; i < 20; i++) {
            if (gme_track_ended(emu)) break;
            gme_play(emu, 2048, buf);
        }
    }

    gme_delete(emu);
    return 0;
}
