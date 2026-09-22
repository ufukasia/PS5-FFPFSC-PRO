
<h1 align="center">🚀 PS5 FFPFSC PRO</h1>

<p align="center">
  PS5 Game Compression Utility
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-Supported-blue">
  <img src="https://img.shields.io/badge/Linux-Supported-yellow">
  <img src="https://img.shields.io/badge/macOS-Supported-lightgrey">
  <img src="https://img.shields.io/badge/Backend-MkPFS%20%2B%20FFPFSC-orange">
  <img src="https://img.shields.io/badge/Version-v1.4.0-green">
  <img src="https://img.shields.io/badge/Fork-ufukasia-blueviolet">
  <img src="https://img.shields.io/badge/UI-EN%20%2F%20TR-informational">
</p>

<p align="center">
  <a href="https://github.com/ufukasia/PS5-FFPFSC-PRO/releases">📥 Download</a> •
  <a href="https://github.com/KINGDKAK/PS5-FFPFSC-PRO">⬆️ Upstream project</a> •
  <a href="https://youtube.com/@KINGDKAK">📺 YouTube</a> •
  <a href="https://ko-fi.com/KINGDKAK">☕ Ko-fi</a>
</p>

---

## 🍴 About this fork / Bu fork hakkında

This is a fork of [KINGDKAK/PS5-FFPFSC-PRO](https://github.com/KINGDKAK/PS5-FFPFSC-PRO).
The compression backend (MkPFS / Bizkut) is untouched — everything below is
interface, workflow and bug-fix work on top of upstream **v1.3.0**.

Bu depo [KINGDKAK/PS5-FFPFSC-PRO](https://github.com/KINGDKAK/PS5-FFPFSC-PRO)
projesinin bir fork'udur. Sıkıştırma arka ucuna (MkPFS / Bizkut) dokunulmamıştır;
aşağıdakiler upstream **v1.3.0** üzerine eklenen arayüz, iş akışı ve hata
düzeltmeleridir.

### ↔ Flexible layout — Esnek tasarım

* The window opens to fit the usable desktop and honours Windows display
  scaling. The old fixed 1400x960 became 1750x1200 at 125% scaling and pushed
  controls (the CPU-core slider among them) off the screen.
* The three columns — queue, progress, details — sit behind **draggable sashes**,
  so any column can be widened or narrowed.
* Every column scrolls independently, so nothing is stranded below the window
  edge on a small screen. Labels re-wrap live as a column is resized.
* New **Reset Layout** button restores the default pane sizes.
* The queue list gained a horizontal scrollbar, and the mouse wheel scrolls the
  list under the pointer instead of the column behind it.

*Pencere, masaüstüne ve Windows ölçeklemesine göre açılır; üç sütun sürüklenerek
genişletilip daraltılabilir, her sütun ayrı kaydırılır, "Reset Layout" ile
varsayılan düzene dönülür.*

### 🌍 Turkish / English interface — Türkçe / İngilizce arayüz

* An **EN / TR** button in the header switches the whole interface live, and the
  choice is remembered between runs.
* Backend log output stays English on purpose, so logs can still be shared for
  support.

*Başlıktaki EN / TR düğmesi arayüzü anında değiştirir ve seçim kaydedilir.*

### ⏭ Skip already-compressed games — Aynı oyunu tekrar sıkıştırmama

* New option **"Skip games that are already compressed"** (on by default).
* Finished games are dropped from the queue before a batch starts, and the
  backend enforces the same rule through a new `--skip-existing` flag — which
  also covers `--batch` runs the GUI cannot pre-check.
* Both the old `TITLEID.ffpfsc` and the new `TITLEID-Game Name.ffpfsc` layouts
  are recognised, so games compressed by earlier versions still count as done.

*Çıktı klasöründe zaten .ffpfsc'si olan oyunlar yeniden sıkıştırılmaz.*

### 🏷 Output named after the game — Oyun ismiyle çıktı

* Output is now `TITLEID-Game Name.ffpfsc` instead of `TITLEID.ffpfsc`, read from
  the game's own `sce_sys/param.json` and falling back to the folder name.
* Characters Windows rejects are replaced rather than dropped
  (`NieR:Automata` → `NieR Automata`), the name is trimmed to a sane length, and
  a title ID already present in the source name is not repeated.

*Çıktı dosyası `OYUNKODU-Oyun Adı.ffpfsc` biçiminde adlandırılır.*

### 🩹 Bug fixes — Hata düzeltmeleri

* **UnicodeEncodeError on Turkish Windows** — with stdout redirected to a pipe,
  Python fell back to the ANSI codepage (cp1254) and crashed on the icons mkpfs
  prints, killing builds that had actually finished. All pipes are UTF-8 now and
  log output degrades instead of raising.
* **exFAT is no longer flagged as 4 GB limited** — only FAT32/FAT caps a single
  file at 4 GB; exFAT exists to lift that limit and is a valid output target.
* **Free space is checked the way mkpfs checks it** — mkpfs reserves free space
  equal to the full *uncompressed* source size before it starts, so that is what
  is verified, before the run rather than hours into it.
* **The space dialog blocks a doomed run** instead of auto-proceeding, and says
  what is missing and by how much.
* **Error hints report the cause that actually holds** rather than blaming the
  output filesystem for every failure.
* Settings toggled in the main window (skip existing, auto-clear temp) are saved
  immediately.
* The updater tracks this fork's releases, and treats "no release published yet"
  as up to date instead of an error.

---

## 📦 About

PS5 FFPFSC PRO is a cross-platform GUI for compressing PlayStation 5 game dumps using MkPFS and FFPFSC.

The application supports Windows, Linux, and macOS.

The goal is simple: make PS5 game compression easy without requiring command-line tools or complicated setup.

Whether you're compressing a single game, batch processing multiple titles, or browsing community compatibility reports, everything can be done from one interface.

---

## 🖼️ Screenshots

### Main Window

![PS5 FFPFSC PRO Main Window](screenshots/main-window.png)

### Community Compatibility Database

![Community Database](screenshots/community-database.png)


### Compression Progress

![Compression Progress](screenshots/compression-progress.png)

---

## ✨ Features

* Compress PS5 game dumps into .ffpfsc
* Flexible layout — resizable, independently scrollable columns (fork)
* English / Turkish interface (fork)
* Skips games that are already compressed (fork)
* Output named after the game: `TITLEID-Game Name.ffpfsc` (fork)
* Supports game folders, .exfat, .ffpkg, .zip, .rar, and .7z
* Drag-and-drop support
* Batch compression
* Multi-image queueing
* Compression tuning options
* Compression presets (Fast, Balanced, Max Compression, Low RAM)
* Automatic update checker
* Live RAM meter
* Automatic retry on out-of-memory errors
* Detailed logs and progress tracking
* Per-game output folders
* Compact mode
* Interactive feature tour
* What's New dialog after updates
* Community Compatibility Database
* APR / AMPR game support
---

## 📂 Supported Inputs

* PS5 game folders
* `.exfat` images
* `.ffpkg` images
* `.zip` archives
* `.rar` archives
* `.7z` archives

---

## 🌐 Community Compatibility Database

After a successful compression, you can optionally submit your results to the community database.

The database allows users to:

* Share compatibility reports
* Report Working / Partial / Not Working / Not Tested Yet status
* Search by game name
* Search by Title ID
* View report counts
* View ShadowMount version information
* Browse compatibility reports directly from the application
* Duplicate submission protection
* Vote-based reporting system
* Submit results directly from the application
* Filter by compatibility status
* Browse over 5,000+ community compatibility reports

Compatibility status is vote-based so one incorrect report cannot override community results.

View the live compatibility database:

https://docs.google.com/spreadsheets/d/1dgu0p7U2yB_mhcUELz-Wkc7Yhs-avoWLY1Gcm0n5XJw/edit?usp=drive_web&ouid=115958744890792485831

Or access it directly from PS5 FFPFSC PRO.

---

## ⚙️ Compression Tuning

Advanced users can fine-tune compression using:

* Compression level selection
* CPU core selection
* Block size selection

Available block sizes:

* Auto
* Auto-Fit
* 16384
* 32768
* 65536

Smaller block sizes may improve results for games containing large numbers of small files.

Compression Presets
* 🚀 Fast
* ⚖️ Balanced
* 🗜️ Max Compression
* 💾 Low RAM

Presets automatically configure compression level, CPU cores, and block size.

---

## 🎮 AMPR / APR Support

PS5 FFPFSC PRO can detect games that require the AMPR emulator.

Features include:

* Automatic PlayGo chunk detection
* Automatic APR title detection
* Automatic AMPR index generation
* Dedicated AMPR folder configuration
* Compatibility reporting support
* Batch mode support

---

📊 Monitoring & Automation


* Live RAM meter
* Automatic update checking
* Windows completion notifications
* Automatic retry on memory errors
* Real-time progress tracking


---

🎓 User Experience


* Interactive feature tour
* What's New dialog after updates
* Full Help / FAQ section
* Detailed logging
* Resizable log panel
* Compact mode



---

## 🚀 Getting Started

1. Download the latest release.
2. Run `PS5_FFPFSC_PRO.exe` — or `RUN.bat` to start `PS5_FFPFSC_PRO_v1.4.0.py` from source
3. Add a game folder, archive, `.exfat`, or `.ffpkg` image.
4. Select your compression settings.
5. Click **Start**.

The application handles the rest.

---

## 🛠️ Common Issues

### Out of Memory

Try:

* Lowering CPU cores
* Lowering compression level
* Closing other applications

### Disk Full

Ensure sufficient free space exists in both:

* Output folder
* Temporary folder

### Write Errors

Verify that:

* Output locations are valid
* Drives are writable
* Storage devices have enough free space

The application provides detailed error messages and recommended fixes whenever possible.

---

## 🙏 Credits

### Compression Backend

* MkPFS
* Bizkut

### Upstream

* Original project and ongoing development: [KINGDKAK](https://github.com/KINGDKAK/PS5-FFPFSC-PRO)
* This fork: [ufukasia](https://github.com/ufukasia/PS5-FFPFSC-PRO)

### Community

Special thanks to everyone testing games, submitting compatibility reports, reporting bugs, and helping improve the project.

---

## 🔗 Links

📺 YouTube
https://youtube.com/@KINGDKAK

☕ Ko-fi
https://ko-fi.com/KINGDKAK

📥 Releases
https://github.com/KINGDKAK/PS5-FFPFSC-PRO/releases

---

## ⚠️ Disclaimer

This project is provided as-is.

Only use content you legally own and follow all applicable laws in your region.

---

⭐ If you find the project useful, consider starring the repository and contributing compatibility reports to help the community.
