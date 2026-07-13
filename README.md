# GameVault

GameVault adalah aplikasi web sederhana untuk menyimpan dan mengelola video gameplay menggunakan MinIO sebagai object storage yang kompatibel dengan Amazon S3.

## Fitur

- Upload video MP4, WEBM, MKV, MOV, dan AVI.
- Simpan metadata judul, nama game, kategori, dan deskripsi.
- Tampilkan daftar object dalam bucket MinIO.
- Cari video berdasarkan judul, nama game, kategori, atau nama file.
- Putar video melalui presigned URL.
- Unduh video.
- Hapus video dari bucket.
- Dashboard jumlah video dan total kapasitas penyimpanan.

## Struktur proyek

```text
gamevault_minio/
├── app.py
├── storage.py
├── templates/
├── static/css/style.css
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

## Menjalankan dengan Docker

1. Pastikan Docker Desktop aktif.
2. Buka terminal pada folder proyek.
3. Jalankan:

```bash
docker compose up --build
```

4. Buka aplikasi: `http://localhost:5000`
5. Buka MinIO Console: `http://localhost:9001`
6. Login MinIO dengan username `minioadmin` dan password `minioadmin`.

Untuk menghentikan aplikasi:

```bash
docker compose down
```

## Menjalankan tanpa Docker untuk aplikasi Flask

MinIO tetap harus aktif pada port 9000.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS atau Linux:

```bash
source .venv/bin/activate
```

Lanjutkan dengan:

```bash
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Pada macOS atau Linux, gunakan `cp .env.example .env`.

## Konfigurasi

Konfigurasi dibaca dari file `.env`.

```env
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=gameplay-videos
MINIO_SECURE=false
SECRET_KEY=ganti-dengan-kunci-rahasia
MAX_UPLOAD_GB=2
PORT=5000
```

## Catatan pemutaran video

Browser biasanya dapat memutar MP4 dan WEBM secara langsung. File MKV atau AVI dapat tersimpan di MinIO, tetapi beberapa browser hanya menyediakan opsi unduh.

## Alur data

1. Pengguna memilih file video dan mengisi metadata.
2. Flask menyimpan file sementara.
3. MinIO SDK mengunggah file sebagai object ke bucket `gameplay-videos`.
4. Metadata disimpan pada object header.
5. Aplikasi membuat presigned URL saat pengguna memutar atau mengunduh video.
