# Balas Utas — skill Claude untuk Threads

Posting utas "yang mau reply *mau* ya..", lalu setiap orang yang membalas langsung dapat link secara otomatis dalam hitungan detik. Balasan otomatis berjalan di server [Zernio](https://zernio.com), jadi tetap jalan walau komputer mati.

Cukup minta ke Claude dengan bahasa biasa:

- *"bikin 10 variasi utas buat webinar X sabtu ini, linknya s.id/abc"*
- *"jadwalkan semua, tanpa poster"*
- *"cek balasan"* · *"majukan jadwalnya mulai hari ini"* · *"matikan setelah acara selesai"*

Claude menulis variasi utas dan balasan, menunjukkan pratinjau, lalu menjadwalkan **setelah kamu setuju**.

## Yang dibutuhkan

1. **Claude Code**: aplikasi desktop Claude (tab Code) atau CLI `claude`.
2. **Python 3.9+** (`python3 --version`).
3. **Akun Zernio** (paket gratis cukup) dengan akun Threads yang sudah terhubung, plus **API key**-nya.

## Pasang

Di Claude Code, ketik:

```
/plugin marketplace add mas-syah/balas-utas
/plugin install balas-utas@balas-utas
```

Simpan API key Zernio **sendiri**, di terminal kamu (jangan ditempel ke chat):

```bash
mkdir -p ~/.balas-utas && nano ~/.balas-utas/zernio_key && chmod 600 ~/.balas-utas/zernio_key
```

Lalu bilang ke Claude: *"setup balas utas"*.

Kalau tidak memakai marketplace, salin folder `skills/balas-utas` ke `~/.claude/skills/`.

## Cara kerja

- Setiap utas = satu file kampanye JSON berisi teks utas, kata kunci (`mau`, `ikut`, `gas`, 🙋 …), kata pengecualian (`gak mau`, `ga bisa` …), dan 1–6 variasi balasan dengan `@{{username}}` dan link.
- `scripts/balas.py` menjadwalkan utas di Zernio dan memasang balasan otomatis **sebelum** utas terbit, jadi tidak ada komentar yang terlewat.
- Setiap orang dibalas sekali per utas.

## Batasan

- Balasannya berupa reply publik, bukan DM.
- Paket gratis Zernio dibatasi 2 akun sosmed per akun Zernio.
- Mematikan otomatis "setelah acara" memakai timer di komputer kamu, jadi komputer harus menyala pada jam itu.

MIT License.
