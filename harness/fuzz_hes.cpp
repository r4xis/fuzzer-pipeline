#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "gme/gme.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // HES header is 0x20 bytes (Hes_Emu::header_size in libgme); anything
    // shorter can never be a valid file, so reject before gme_load_data.
    if (size < 0x20) return 0;

    Music_Emu *emu = gme_new_emu(gme_hes_type, 44100);
    if (!emu) return 0;

    gme_err_t err = gme_load_data(emu, data, size);
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

    err = gme_start_track(emu, 0);
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
