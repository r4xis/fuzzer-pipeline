/*
 * fuzz_afdko_cff2.cpp — AFDKO CFF2 / variable-font harness.
 *
 * Hedef: c/shared/cffread_abs.cpp (cfrNew/cfrBegFont) — cffread.c'den
 * FARKLI olarak CFF2 ve modern variable-font (fvar/avar/ItemVariationStore)
 * yollarini parse eder. Asil bug yuzeyi: varsupport.cpp + t2cstr.cpp.
 *
 * Harness ne yapiyor (adim adim):
 *   1. Fuzzer bize bir byte dizisi (data,size) verir.
 *   2. Tum input'u font verisi sayariz, bir bellek-akisi (stream) arkasina
 *      koyariz (kesme yok -- gercek bir .otf dogrudan seed olabilir).
 *   3. cfrNew ile parser'i baslatir, cfrBegFont ile parse ettiririz (UDV=0,
 *      yani varsayilan instance -- parser yine de fvar/avar tablolarini
 *      okur, asil bug yuzeyi budur).
 *   4. cfrIterateGlyphs ile tum glyph'leri okuturuz (charstring/blend).
 *   5. cfrEndFont + cfrFree ile temizleriz.
 */

#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>	// __AFL_FUZZ_TESTCASE_LEN expands to a bare read(0, ...) call

#include "ctlshare.h"       /* ctlMemoryCallbacks, ctlStreamCallbacks */
#include "cffread_abs.h"    /* cfrNew, cfrBegFont, cfrIterateGlyphs ... */
#include "absfont.h"        /* abfGlyphCallbacks, abfTopDict */

#ifdef __AFL_FUZZ_TESTCASE_LEN
__AFL_FUZZ_INIT();
#endif

/* ================================================================== *
 * 1) BELLEK YONETIMI callback'i.
 *    cffread_abs tek bir "manage" fonksiyonu ister: realloc gibi calisir.
 *      - size>0, old==NULL  -> yeni ayir (malloc)
 *      - size>0, old!=NULL  -> yeniden boyutlandir (realloc)
 *      - size==0            -> serbest birak (free), NULL dondur
 * ================================================================== */
static void *mem_manage(ctlMemoryCallbacks *cb, void *old, size_t size) {
    (void)cb;
    if (size == 0) { free(old); return NULL; }
    return realloc(old, size);
}

/* ================================================================== *
 * 2) VERI KAYNAGI (stream).
 *    Font byte'larini bellekte tutan yapi. Parser dosya acmaz; bizim
 *    stream callback'lerimizi cagirir, biz de bu buffer'dan veri veririz.
 * ================================================================== */
typedef struct {
    const uint8_t *data;
    long           size;
    long           pos;
} MemStream;

/* open(): stream'i "ac" — biz zaten bellekteyiz, sadece pozisyonu sifirla
 * ve stream nesnesi olarak kendi yapimizi don. */
static void *stm_open(ctlStreamCallbacks *cb, int id, size_t size) {
    (void)id; (void)size;
    MemStream *s = (MemStream *)cb->direct_ctx;
    s->pos = 0;
    return s;   /* stream handle olarak kendimizi veriyoruz */
}

/* seek(): verideki belirli bir konuma git. Kendimizi koruyoruz:
 * sinir disi offset -> hata (-1). */
static int stm_seek(ctlStreamCallbacks *cb, void *stream, long offset) {
    (void)cb;
    MemStream *s = (MemStream *)stream;
    if (offset < 0 || offset > s->size) return -1;
    s->pos = offset;
    return 0;
}

/* tell(): su an neredeyiz? */
static long stm_tell(ctlStreamCallbacks *cb, void *stream) {
    (void)cb;
    return ((MemStream *)stream)->pos;
}

/* read(): mevcut pozisyondan itibaren veri bloğunu ver.
 * ONEMLI: sfnt reader bir "read" cagirisiyla bir blok alir, sonra o
 * blok icinde seek'lerle gezinir ve pozisyonu degistirip tekrar read
 * cagirabilir. O yuzden pozisyonu SONA ATMIYORUZ — her read mevcut
 * pozisyondan kalan tum veriyi verir, pozisyonu oldugu gibi birakir.
 * (seek pozisyonu yonetir; read sadece oradaki veriyi gosterir.) */
static size_t stm_read(ctlStreamCallbacks *cb, void *stream, char **ptr) {
    (void)cb;
    MemStream *s = (MemStream *)stream;
    if (s->pos < 0 || s->pos >= s->size) { *ptr = NULL; return 0; }
    *ptr = (char *)(s->data + s->pos);
    return (size_t)(s->size - s->pos);
}

/* status(): hata durumu yok, 0 don. */
static int stm_status(ctlStreamCallbacks *cb, void *stream) {
    (void)cb; (void)stream; return 0;
}

/* close(): kapatacak bir sey yok (bellekteyiz). */
static int stm_close(ctlStreamCallbacks *cb, void *stream) {
    (void)cb; (void)stream; return 0;
}

/* ================================================================== *
 * 3) GLYPH callback'leri — hepsi NO-OP (bos).
 *    cfrIterateGlyphs her glyph'in cizim operatorleri icin bunlari
 *    cagirir. Biz cizmek istemiyoruz, sadece parser'in charstring'i
 *    yorumlamasini istiyoruz; o yuzden hepsi bos. 'beg' 0 donmeli
 *    (devam et anlaminda). */
/* beg(): parser glyph bilgisini (info) burada verir. ONEMLI: parser
 * daha sonra cb->info uzerinden bu bilgiye erisir (t2cParse icinde
 * glyph->info->flags). O yuzden info'yu cb->info'ya KAYDETMELIYIZ —
 * yoksa NULL dereference / segfault olur. (Standart absfont callback'i
 * de aynen bunu yapar.) 0 = devam et. */
static int   g_beg(abfGlyphCallbacks *cb, abfGlyphInfo *info) { cb->info = info; return 0; }
static void  g_width(abfGlyphCallbacks *cb, float h) { (void)cb; (void)h; }
static void  g_move(abfGlyphCallbacks *cb, float x, float y) { (void)cb; (void)x; (void)y; }
static void  g_line(abfGlyphCallbacks *cb, float x, float y) { (void)cb; (void)x; (void)y; }
static void  g_curve(abfGlyphCallbacks *cb, float x1,float y1,float x2,float y2,float x3,float y3){(void)cb;(void)x1;(void)y1;(void)x2;(void)y2;(void)x3;(void)y3;}
static void  g_stem(abfGlyphCallbacks *cb, int f, float e0, float e1){(void)cb;(void)f;(void)e0;(void)e1;}
static void  g_flex(abfGlyphCallbacks *cb, float d, float x1,float y1,float x2,float y2,float x3,float y3,float x4,float y4,float x5,float y5,float x6,float y6){(void)cb;(void)d;(void)x1;(void)y1;(void)x2;(void)y2;(void)x3;(void)y3;(void)x4;(void)y4;(void)x5;(void)y5;(void)x6;(void)y6;}
static void  g_genop(abfGlyphCallbacks *cb, int cnt, float *args, int op){(void)cb;(void)cnt;(void)args;(void)op;}
static void  g_seac(abfGlyphCallbacks *cb, float adx, float ady, int bchar, int achar){(void)cb;(void)adx;(void)ady;(void)bchar;(void)achar;}
static void  g_end(abfGlyphCallbacks *cb) { (void)cb; }

/* ================================================================== *
 * 4) ASIL TEST: bir font byte dizisini CFF2 parser'ina ver.
 * ================================================================== */
static void run_one(const uint8_t *data, size_t size) {
    enum { MAX_AXES = 15 };
    if ((long)size < 4)
        return;

    float udv[MAX_AXES];
    memset(udv, 0, sizeof(udv));   /* default instance (eksen ortasi) */

    MemStream stream = { data, (long)size, 0 };

    ctlMemoryCallbacks mem_cb;
    memset(&mem_cb, 0, sizeof(mem_cb));
    mem_cb.ctx = NULL;
    mem_cb.manage = mem_manage;

    ctlStreamCallbacks stm_cb;
    memset(&stm_cb, 0, sizeof(stm_cb));
    stm_cb.direct_ctx = &stream;   /* open() bunu kullanacak */
    stm_cb.open   = stm_open;
    stm_cb.seek   = stm_seek;
    stm_cb.tell   = stm_tell;
    stm_cb.read   = stm_read;
    stm_cb.status = stm_status;
    stm_cb.close  = stm_close;
    /* write, xml_read NULL kalir — CFF2 okuma bunlari kullanmaz */

    cfrCtx h = cfrNew(&mem_cb, &stm_cb, CFR_CHECK_ARGS);
    if (h == NULL) return;

    /* cfrBegFont(h, flags, origin, ttcIndex, &top, UDV)
     * flags = CFR_UPDATE_OPS: cfembed.cpp'nin kullandigi, tam parse.
     * origin=0: parser sfnt tablo dizininden CFF/CFF2'yi kendi bulur. */
    abfTopDict *top = NULL;
    if (cfrBegFont(h, CFR_UPDATE_OPS, 0, 0, &top, udv) == 0) {
        abfGlyphCallbacks gcb;
        memset(&gcb, 0, sizeof(gcb));
        gcb.direct_ctx = NULL;
        gcb.beg = g_beg;   gcb.width = g_width; gcb.move = g_move;
        gcb.line = g_line; gcb.curve = g_curve; gcb.stem = g_stem;
        gcb.flex = g_flex; gcb.genop = g_genop; gcb.seac = g_seac;
        gcb.end = g_end;

        cfrIterateGlyphs(h, &gcb);

        cfrEndFont(h);
    }

    cfrFree(h);
}

int main(int argc, char **argv)
{
    // Runtime dispatch, not a compile-time #ifdef: triage/run_triage.sh runs
    // CASR as `casr-afl ... -- /fuzzing/harness @@`, which puts the crash
    // file in argv[1] regardless of how the binary was built. An AFL/persistent
    // build must still honor that convention -- if the AFL branch were chosen
    // at compile time, an AFL-instrumented binary given a file argument would
    // ignore it, read whatever is on stdin instead, see no crash, and CASR
    // would emit no .casrep -- silently dropping the finding before it ever
    // reaches the DB. File mode below runs identically in a plain build and
    // an AFL-instrumented one, and never touches any AFL macro, so
    // `harness <file>` always means "replay this one input".
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
    // file argument) -- see docker-compose.yml's `-- harness` convention.
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
