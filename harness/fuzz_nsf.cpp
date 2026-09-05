#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "gme/gme.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 17) return 0;  // son byte track selector için ayrılıyor

    // Format kilitleme — auto-detect NSF'i HES'e kaçırıyordu, engelliyoruz
    Music_Emu *emu = gme_new_emu(gme_nsf_type, 44100);
    if (!emu) return 0;

    gme_err_t err = gme_load_data(emu, data, size - 1);
    if (err) {
        gme_delete(emu);
        return 0;
    }

    gme_set_fade(emu, 1000);

    int track_count = gme_track_count(emu);
    if (track_count <= 0) {
        gme_delete(emu);
        return 0;
    }

    // Son byte input içinden track seç — 3 track yerine 1 track çalıştır
    int track = data[size - 1] % track_count;

    err = gme_start_track(emu, track);
    if (!err) {
        short buf[1024];
        for (int i = 0; i < 15; i++) {
            if (gme_track_ended(emu)) break;
            gme_play(emu, 1024, buf);
        }
    }

    gme_delete(emu);
    return 0;
}
