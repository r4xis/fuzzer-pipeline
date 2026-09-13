# Tasarım Brief'i — Crash Disclosure Frontend

## Proje Ne Hakkında

Bu, bir güvenlik araştırmacısının (fuzzing ile bulduğu) bug'ları herkese açık
olarak yayınladığı bir "vulnerability disclosure" sitesi — CVE veritabanları,
GitHub Security Advisories, Project Zero'nun blog'una yakın bir ciddiyet ve
teknik ton hedefleniyor. Bu bir "bakın ne yaptım" tarzı pazarlama/portfolyo
sitesi değil; ziyaretçi (işe alım uzmanı, başka bir güvenlik araştırmacısı,
etkilenen bir geliştirici) bulunan bug'ları güvenilir, doğrulanabilir bir
şekilde inceleyebilmeli, disclosed olanların proof-of-concept dosyalarını
indirebilmeli.

Fuzzlanan hedef: açık kaynaklı bir ses/müzik emülatörü kütüphanesi (libgme).
Kütüphane farklı retro konsol ses formatlarını (NES/NSF, Sega/VGM gibi)
destekliyor; her format ayrı bir "target" olarak fuzzlanıyor, aynı programın
altında birden fazla target birikebiliyor (ileride yeni programlar/projeler
de eklenebilir — şema buna göre tasarlandı).

## Mevcut Teknik Yapı (Değiştirilebilir, Ama Bilgi Amaçlı)

- React + Vite, şu an tek CSS dosyası (src/index.css), component'ler:
  ProgramList → TargetList → CrashList → CrashDetail (tıklamayla ilerleyen
  bir hiyerarşi, geri butonlarıyla).
- Şu anki renk sistemi: koyu tema, İnk-siyah arkaplan (#0B0D10), IBM Plex
  Sans (body) + IBM Plex Mono (kod/path/hash için) yazı tipi ikilisi,
  severity'ye göre renklendirme (kırmızı=risk, sarı=yeni, yeşil=çözüldü).
- Sayfada bir "sinyal izi" (osiloskop tarzı, ince, animasyonlu SVG çizgi)
  motifi var — ses çipi emülasyonu temasına gönderme, crash/trace kelime
  oyunuyla kavramsal bağı var.
- **Bu yapı bir başlangıç noktası, zorunlu değil.** Genel ruhu (ciddi,
  teknik, "log/bülten" hissi, gösterişli SaaS kart tasarımından kaçınma)
  korumak yeterli — renk, tipografi, layout detaylarında serbestsin,
  yaratıcı ol.

## Gerçek Backend API (Bunlara Sadık Kal, Var Olmayan Endpoint Uydurma)

```
GET /programs
  → {"programs": [{id, name, repo_url}]}

GET /targets?program_id=X
  → {"targets": [{id, program_id, focus, harness_version}]}
  focus değerleri örnek: "NSF", "VGM" (formata göre değişir)

GET /crashes?visibility=private&status=Y&target_id=Z
  → {"count": N, "crashes": [{id, crash_line, severity_type, severity_desc,
      visibility, status, discovered_at, target_focus, program_name}]}
  visibility: "public" | "private" (default: sadece public döner,
    admin görünümü için visibility=private geçilmeli)
  status: "new" | "triaged" | "reported" | "duplicate"

GET /crashes/{id}?visibility=private
  → tam detay: {..., severity_explain, stacktrace: [...], asan_summary,
      source_context: [...], poc_file_size, poc_file_sha256}
  stacktrace ve source_context birer STRING ARRAY (her eleman bir satır).
  source_context içinde crash satırı "--->" öneki ile işaretli gelir,
  örn: "--->255    write_pcm(vgm_time, *pcm_pos++);"

GET /crashes/{id}/download
  → PoC dosyasını indirir (sadece visibility=public olanlarda çalışır,
    backend zaten 403 ile bunu koruyor)

PATCH /crashes/{id}/status
  body: {"status": "new" | "triaged" | "reported" | "duplicate"}
  → crash'in durumunu günceller

GET /sessions/{id}/history
  → {"session_id": id, "history": [{recorded_at, coverage_pct, total_execs}]}
  Zaman sıralı coverage geçmişi — bir fuzzing session'ının coverage'ının
  zaman içinde nasıl geliştiğini gösterir.

GET /sessions/{id}/instances
  → {"instances": [{instance_name, coverage_pct, execs_per_sec,
      crashes_saved, recorded_at}]}
  instance_name değerleri: "fuzzer0", "fuzzer1", "fuzzer2", "fuzzer3".
  ÖNEMLİ İSİMLENDİRME KURALI: fuzzer0 = MASTER (AFL++ -M modu),
  fuzzer1/2/3 = SLAVE (AFL++ -S modu). Bu ayrımı frontend'de görsel
  olarak göster (örn. "Master" / "Slave" etiketi).
```

Coverage/execs verisi 15 dakikada bir otomatik güncelleniyor (cron ile),
yani "canlı" dediğimiz şey aslında ~15 dakikalık aralıklarla yenilenen bir
veri — gerçek zamanlı WebSocket değil, polling ile yeterli.

## Kesin Tasarım Gereksinimleri

### 1. Header, Footer, Sidebar eklenmeli (şu an hiçbiri yok)
- **Header:** Site başlığı/logo. Sağ tarafta bir **LIVE/CLOSED** durumu
  göstergesi (yeşil nokta = live, kırmızı/gri nokta = closed) — o an
  görüntülenen target'ın fuzzing'i aktif mi değil mi. Heuristic: ilgili
  target'ın en son `recorded_at` değeri (history veya instances
  endpoint'inden) şu andan geriye ~20 dakikadan daha yeniyse LIVE,
  değilse CLOSED say (15 dakikalık cron aralığına makul bir tampon payı).
  Ayrıca header'da (veya footer'da) küçük GitHub ve LinkedIn ikon
  linkleri olsun (placeholder URL'ler kullan, gerçek linkler sonra
  eklenecek).
- **Footer:** Projenin kısa bir açıklaması (bu sitenin ne olduğu,
  responsible disclosure yaklaşımına bir cümlelik referans), belki
  fuzzing pipeline'ının kendisinin GitHub reposuna bir link (placeholder).
- **Sidebar:** Program → Target ağacını sürekli görünür kılan bir
  navigasyon. Kullanıcı derine indikçe (crash listesi, crash detayı)
  sidebar'dan geri/başka bir target'a hızlıca geçebilmeli — şu anki
  "her seferinde geri butonuna basarak dön" akışının üstüne, kalıcı bir
  hızlı-geçiş katmanı olarak düşün.

### 2. Raporlanmamış crash'lerin detayı gizli kalsın
`status !== "reported"` olan bir crash'e tıklanınca stack trace, kaynak
kod context'i, ASAN özeti ve indirme butonu GÖSTERİLMESİN. Onun yerine
"Bu bulgu henüz inceleme/açıklama sürecinde" gibi kilitli, nötr bir durum
ekranı göster (severity ve genel açıklama gibi zaten zararsız bilgiler
kalabilir, teknik detay sızdırılmasın). Bu, backend'deki visibility
kontrolünün ÜSTÜNE eklenen ikinci bir katman — ikisi birlikte çalışacak.

### 3. Sinyal izi (osiloskop çizgisi) canlı tepki versin
Şu an tamamen statik/dekoratif duran bu motif, yeni bir crash bulunduğunda
görsel olarak "sıçrasın" / tepki versin. Mekanizma: frontend belirli
aralıklarla (örn. 30-60 saniyede bir) ilgili target'ın crash sayısını
polling ile kontrol etsin (mevcut /crashes?target_id=X endpoint'i sayım
için yeterli); önceki poll'a göre sayı arttıysa çizgide kısa, belirgin bir
"spike" animasyonu tetiklensin, sonra normal/idle dalga formuna dönsün.
Yeni bir backend endpoint'i gerekmiyor, mevcut veriyle çözülebilir.

### 4. Coverage için ayrı, özenle ölçeklenmiş bir grafik
`GET /sessions/{id}/history` verisini kullanarak zaman içindeki coverage
değişimini gösteren bir grafik ekle. KRİTİK: farklı session'ların coverage
değerlerini (örneğin biri %9, biri %50) aynı sabit 0-100 lineer eksende
göstermek düşük coverage'ı "neredeyse boş/çirkin" gösterir — bunun yerine
her grafiğin y ekseni kendi session'ının gerçek veri aralığına göre
otomatik ölçeklensin (min/max'a göre uygun padding ile), ya da değerin
kendisini net okunur şekilde etiketleyen bir tasarım kullan. Amaç: %9'luk
bir coverage'ın kendi grafiğinde anlamlı ve okunabilir görünmesi, %50'lik
başka bir target'la kıyaslanınca "başarısız" hissi vermemesi.

### 5. Master/Slave fuzzer instance'ları ayrı gösterilsin
`GET /sessions/{id}/instances` verisini kullanarak, bir target'ın altında
çalışan fuzzer0 (Master) ve fuzzer1/2/3 (Slave) instance'larının her
birinin kendi coverage/execs/crash sayısını ayrı ayrı (örn. küçük
kartlar veya bir tablo olarak) göster. Master'ı görsel olarak hafifçe
öne çıkarabilirsin (örn. küçük bir "M" rozeti), slave'leri kendi
aralarında eşit ağırlıkta göster.

### 6. Raporlanan (disclosed) crash'ler için görünüm
Ayrı bir sayfa AÇMA — bunun yerine crash listesi görünümüne bir
filtre/sekme ekle (örn. "Tümü / Raporlanan"), mevcut
`GET /crashes?status=reported` parametresini kullanarak. Bu, backend'de
zaten var olan bir yeteneği yeniden kullanıyor, yeni bir sayfa/route
karmaşıklığı eklemiyor.

## Serbest Bırakılan Alanlar (Yaratıcılığın İçin)

- Renk paleti, tipografi, layout detayları — mevcut sistem bir başlangıç
  noktası, istersen tamamen yeniden düşünebilirsin.
- Sinyal izi motifinin tam görsel dilini (nasıl "spike" edeceği, renk
  değişimi mi yoksa genlik değişimi mi kullanacağı) sen belirle.
- Coverage grafiğinin tam görsel formatını (çizgi grafik, alan grafik,
  sparkline tarzı küçük bir widget) sen seç — önemli olan yukarıdaki
  ölçekleme prensibi.
- Sidebar'ın tam etkileşim modelini (daralan/genişleyen, her zaman açık,
  mobilde nasıl davranacağı) sen tasarla.

## İstenmeyen Şeyler

- Şablon bir SaaS dashboard hissi (birbirinin aynı yuvarlak kartlar, aşırı
  gölge/gradient) — bu bir güvenlik bülteni, pazarlama sitesi değil.
- Var olmayan backend endpoint'leri veya alanları uydurmak — yukarıdaki
  API listesine sadık kal, eksik bir veri gerekiyorsa bunu açıkça belirt,
  varsayma.
- Gerçek zamanlı WebSocket gerektiren bir tasarım — polling yeterli,
  veri zaten 15 dakikada bir güncelleniyor.
