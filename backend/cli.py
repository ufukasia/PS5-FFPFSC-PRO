#!/usr/bin/env python3
"""PS5 FFPFSC PRO — backend wrapper (MkPFS 0.0.9+)"""
from __future__ import annotations  # makes str|None / list[X] work on Python 3.7+
import sys
import os


# ── Console encoding safety ───────────────────────────────────────────────────
# When stdout/stderr are redirected (the GUI reads them through a pipe) Python
# falls back to the ANSI locale codepage — cp1254 on Turkish Windows — which
# cannot encode the icons mkpfs prints, killing an otherwise finished build with
# UnicodeEncodeError. Force UTF-8 here and for every child process we spawn.
def _force_utf8_io() -> None:
    for _stream in (sys.stdout, sys.stderr):
        try:
            if "UTF" in ((getattr(_stream, "encoding", "") or "").upper()):
                continue
            _reconfigure = getattr(_stream, "reconfigure", None)
            if _reconfigure is not None:
                _reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    # Inherited by the mkpfs subprocess launched further below.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8:replace")


_force_utf8_io()

# ── Bundled mkpfs detection ───────────────────────────────────────────────────
# When this script lives inside a 'backend/' folder, look for 'backend/mkpfs/'
# and add 'backend/' to sys.path so 'import mkpfs' resolves to the bundled copy.
_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_BUNDLED_MKPFS = os.path.join(_CLI_DIR, "mkpfs", "__main__.py")
if os.path.isfile(_BUNDLED_MKPFS) and _CLI_DIR not in sys.path:
    sys.path.insert(0, _CLI_DIR)

# ── Frozen-mode internal mkpfs intercept ─────────────────────────────────────
if len(sys.argv) > 1 and sys.argv[1] == "--mkpfs-internal":
    try:
        from mkpfs.cli import cli_mkpfs_main
        sys.exit(cli_mkpfs_main(sys.argv[2:]))
    except Exception as e:
        print(f"[ERROR] Internal MkPFS call failed: {e}", file=sys.stderr)
        sys.exit(1)

import argparse
import contextlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_title_id_from_name(name: str) -> str:
    match = re.search(r'\b([A-Z]{4}\d{5})\b', name, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    fallback = name
    for suffix in [".exfat", ".ffpkg", "-app0", "-app", "-patch0", "-patch"]:
        if fallback.lower().endswith(suffix):
            fallback = fallback[:-len(suffix)]
    return fallback


def get_title_id(item_path: Path) -> str:
    if item_path.is_dir():
        param_path = item_path / "sce_sys" / "param.json"
        try:
            if param_path.is_file():
                with open(param_path, encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("titleId") or data.get("title_id") or ""
        except Exception as e:
            print(f"[WARN] Could not parse param.json for title ID: {e}")
    return get_title_id_from_name(item_path.name)


_DISK_IMAGE_SUFFIXES = {'.exfat', '.ffpkg'}

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def get_title_name(item_path: Path) -> str:
    """Human-readable game name: the param.json title, else the file/folder name."""
    if item_path.is_dir():
        param_path = item_path / "sce_sys" / "param.json"
        try:
            if param_path.is_file():
                with open(param_path, encoding='utf-8') as f:
                    data = json.load(f)
                name = data.get("titleName") or ""
                if not name:
                    localized = data.get("localizedParameters") or {}
                    key = localized.get("defaultLanguage") or "en-US"
                    name = (localized.get(key) or {}).get("titleName") or ""
                if name:
                    return str(name)
        except Exception:
            pass
        return item_path.name

    name = item_path.name
    for suffix in _DISK_IMAGE_SUFFIXES:
        if name.lower().endswith(suffix):
            return name[:-len(suffix)]
    return name


def sanitize_filename(text: str, max_length: int = 60) -> str:
    """Strip characters Windows rejects and trim to a sane length."""
    # Replaced with a space, not deleted, so "NieR:Automata" reads "NieR Automata".
    cleaned = _INVALID_FILENAME_CHARS.sub(" ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-_")
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" .-_")
    return cleaned


_TITLE_ID_PATTERN = re.compile(r'^[A-Z]{4}\d{5}$')


def build_output_stem(item_path: Path, title_id: str) -> str:
    """Compose 'TITLEID-Game Name' for the output file.

    The source name normally already carries the title ID ("PPSA03974 Cyberpunk
    2077"), so it is removed from the name part first — otherwise the result
    would read 'PPSA03974-PPSA03974 Cyberpunk 2077'.

    When no real title ID could be parsed, `get_title_id` hands back the whole
    source name as a fallback; stripping that from itself would mangle the
    result, so the name is used on its own instead.
    """
    name = get_title_name(item_path)
    tid = (title_id or "").strip()
    is_real_id = bool(_TITLE_ID_PATTERN.match(tid.upper()))

    if is_real_id:
        name = re.sub(re.escape(tid), "", name, flags=re.IGNORECASE)
        # Tidy what the removal leaves behind: "Silent Hill f []" -> "Silent Hill f"
        name = re.sub(r"[\[\(\{]\s*[\]\)\}]", " ", name)
        name = re.sub(r"[\s._-]{2,}", " ", name)

    name = sanitize_filename(name)
    if not is_real_id:
        return name or sanitize_filename(tid, 32) or "output"

    tid_clean = sanitize_filename(tid, 32)
    if not name or name.upper() == tid_clean.upper():
        return tid_clean
    return f"{tid_clean}-{name}"


def find_existing_outputs(out_dir: Path, title_id: str) -> list[Path]:
    """Return .ffpfsc files already produced for this title.

    Matches both the old 'TITLEID.ffpfsc' layout and the current
    'TITLEID-Game Name.ffpfsc' one, so games compressed by earlier versions are
    still recognised as done.
    """
    tid = (title_id or "").strip().upper()
    if not tid:
        return []
    try:
        if not out_dir.is_dir():
            return []
    except OSError:
        return []

    found: list[Path] = []
    try:
        for path in out_dir.glob("*.ffpfsc"):
            try:
                if not path.is_file() or path.stat().st_size <= 0:
                    continue
            except OSError:
                continue
            stem = path.stem.upper()
            if stem == tid or any(stem.startswith(tid + sep) for sep in ("-", " ", "_")):
                found.append(path)
    except OSError:
        pass
    return found


def find_game_items(path: Path, batch: bool = False) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() in _DISK_IMAGE_SUFFIXES:
            return [path]
        print(f"[ERROR] Unsupported file type: {path.name}. Supported: .exfat, .ffpkg, or a game folder.")
        sys.exit(1)

    print(f"[INFO] Scanning for game folder(s) and disk image(s) (.exfat / .ffpkg) in {path}...")
    valid_items: list[Path] = []

    # Walk the tree once, pruning descent into found game roots so nested
    # sce_sys/eboot.bin structures inside a game don't produce false duplicates.
    game_roots: set[Path] = set()
    for dirpath, subdirs, filenames in os.walk(path):
        curr = Path(dirpath)

        # Skip if we're already inside a found game root
        if any(curr == r or r in curr.parents for r in game_roots):
            subdirs.clear()
            continue

        for f in filenames:
            if Path(f).suffix.lower() in _DISK_IMAGE_SUFFIXES:
                valid_items.append(curr / f)

        if (curr / "eboot.bin").is_file() and (curr / "sce_sys" / "param.json").is_file():
            valid_items.append(curr)
            game_roots.add(curr)
            subdirs.clear()  # don't recurse into the game folder

    seen: set[Path] = set()
    deduped: list[Path] = []
    for item in valid_items:
        r = item.resolve()
        if r not in seen:
            seen.add(r)
            deduped.append(item)
    valid_items = deduped

    if not valid_items:
        print(f"[ERROR] Could not find any valid game folders or disk images (.exfat / .ffpkg) in {path}.")
        sys.exit(1)

    if not batch and len(valid_items) > 1:
        print(f"[ERROR] Multiple game folders/files found in {path}:")
        for item in valid_items:
            print(f"  - {item}")
        print("Use --batch to process all.")
        sys.exit(1)

    if not batch:
        print(f"[OK] Found game source at {valid_items[0]}")
    else:
        print(f"[OK] Found {len(valid_items)} game item(s) for batch processing.")
    return valid_items


# Only the legacy FAT family caps a single file at 4 GB. exFAT was created
# specifically to lift that limit and handles multi-hundred-GB files fine, so it
# must NOT be treated as a blocker here.
_FAT32_FILESYSTEMS = ("FAT32", "FAT", "FAT16")
_FAT32_MAX_FILE_BYTES = 4 * 1024 ** 3 - 1


def get_filesystem_type(path: Path) -> str:
    """Return the filesystem label ('NTFS', 'exFAT', ...) for `path`, or ''."""
    try:
        import ctypes as _ct
        probe = path.resolve()
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        drive = str(probe)[:3]
        buf = _ct.create_unicode_buffer(64)
        _ct.windll.kernel32.GetVolumeInformationW(drive, None, 0, None, None, None, buf, _ct.sizeof(buf))
        return buf.value.strip()
    except Exception:
        return ""


def get_free_space(path: Path) -> int:
    """Return free bytes on the volume holding `path`, or -1 when unknown."""
    try:
        probe = path.resolve()
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        return shutil.disk_usage(str(probe)).free
    except Exception:
        return -1


def get_source_size(item: Path) -> int:
    """Return the raw byte size of a game folder or disk image, or -1."""
    try:
        if item.is_file():
            return item.stat().st_size
        return sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
    except Exception:
        return -1


def _gb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 ** 3):.1f} GB"


def preflight_output_checks(source_item: Path, output_path: Path) -> list[str]:
    """Return blocking reasons that make this output destination unusable.

    Catches the two failures that otherwise waste a whole run: a FAT32 output
    drive (4 GB per-file ceiling) and a destination with less free space than
    mkpfs demands. mkpfs requires free space >= the *uncompressed* source size,
    so mirror that rule exactly rather than guessing at the packed size.

    exFAT is deliberately not treated as a blocker: it supports files far beyond
    4 GB and is a perfectly valid output target.
    """
    reasons: list[str] = []
    source_size = get_source_size(source_item)
    out_fs = get_filesystem_type(output_path)
    free = get_free_space(output_path)

    if out_fs in _FAT32_FILESYSTEMS and source_size > _FAT32_MAX_FILE_BYTES:
        reasons.append(
            f"OUTPUT DRIVE IS {out_fs}  ->  4 GB per-file limit.\n"
            f"[ERROR]   The source is {_gb(source_size)}, so the .ffpfsc may exceed 4 GB "
            f"and cannot be written there.\n"
            f"[ERROR]   Fix: pick an output folder on an NTFS or exFAT drive."
        )

    if source_size > 0 and 0 <= free < source_size:
        reasons.append(
            f"NOT ENOUGH FREE SPACE ON THE OUTPUT DRIVE.\n"
            f"[ERROR]   mkpfs reserves free space equal to the uncompressed source size,\n"
            f"[ERROR]   even though the finished file ends up smaller.\n"
            f"[ERROR]   Required: {_gb(source_size)}   Available: {_gb(free)}   "
            f"Short by: {_gb(source_size - free)}\n"
            f"[ERROR]   Fix: free up space, or pick an output folder on a larger drive."
        )

    return reasons


def _mkpfs_error_hint(exc: subprocess.CalledProcessError, output_path: Path,
                      source_item: Path | None = None) -> None:
    """Print a clear [ERROR] summary when mkpfs returns a non-zero exit code.

    Reports the condition that actually holds — a FAT output drive is not
    automatically the reason a run failed, so it is no longer assumed to be.
    """
    print(f"[ERROR] mkpfs failed with exit code {exc.returncode}.", flush=True)

    reasons = preflight_output_checks(source_item, output_path) if source_item else []
    if reasons:
        for reason in reasons:
            print(f"[ERROR] {reason}", flush=True)
        return

    fs_label = get_filesystem_type(output_path)
    fs_note = (
        f"[ERROR]   OUTPUT folder  ->  drive is {fs_label}; files over 4 GB need NTFS or exFAT\n"
        if fs_label in _FAT32_FILESYSTEMS
        else "[ERROR]   OUTPUT folder  ->  ensure the drive has enough free space\n"
    )
    print(
        f"[ERROR] Output path: {output_path}\n"
        f"[ERROR] Settings to check:\n"
        f"{fs_note}"
        f"[ERROR]   TEMP folder    ->  needs ~1.5x the game size of free space during compression\n"
        f"[ERROR]   CPU cores      ->  try lowering to 2 or 1 if RAM could be the cause\n"
        f"[ERROR]   Level          ->  try 5 if the default (9) runs out of memory",
        flush=True,
    )


def _locate_mkpfs() -> tuple[list[str], str | None]:
    """Return (cmd_base, cwd) for invoking mkpfs."""
    # Frozen EXE — use internal bundle
    if getattr(sys, "frozen", False):
        print("[INFO] Running in packaged/frozen environment. Using internal MkPFS bundle.")
        return [sys.executable, "--mkpfs-internal"], None

    # Bundled package next to this script (backend/mkpfs/)
    if os.path.isfile(_BUNDLED_MKPFS):
        print(f"[INFO] Using bundled MkPFS package at {_CLI_DIR}")
        return [sys.executable, "-m", "mkpfs"], _CLI_DIR

    # Sibling workspace (legacy detection)
    parent_dir = Path(__file__).resolve().parent.parent
    try:
        for sibling in sorted(parent_dir.iterdir()):
            if sibling.is_dir() and (sibling / "mkpfs" / "__main__.py").is_file():
                print(f"[INFO] Using local workspace directory at {sibling}")
                return [sys.executable, "-m", "mkpfs"], str(sibling)
    except Exception:
        pass

    # System PATH
    if shutil.which("mkpfs"):
        print("[INFO] Using system mkpfs from PATH.")
        return ["mkpfs"], None

    # Auto-install via pip
    print("[INFO] MkPFS not found. Installing automatically via pip...")
    res = subprocess.run(
        [sys.executable, "-m", "pip", "install", "mkpfs==0.0.9"],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        print("[ERROR] Failed to install mkpfs. Please install it manually: pip install mkpfs")
        print(res.stderr)
        sys.exit(1)
    print("[OK] MkPFS 0.0.9 installed successfully.")
    return [sys.executable, "-m", "mkpfs"], None


# ─────────────────────────────────────────────────────────────────────────────
# MkPFS wrappers
# ─────────────────────────────────────────────────────────────────────────────

def pack_folder_single_pass(
    game_folder: Path,
    ffpfsc_path: Path,
    mkpfs_cmd_base: list[str],
    mkpfs_cwd: str | None,
    *,
    verify_enabled: bool = False,
    compression_level: int = 9,
    cpu_count: int = 0,
    threshold_gain: int = 5,
    block_size: str = "auto",
    verbose: bool = False,
    temp_folder: Path | None = None,
) -> None:
    print(f"[INFO] Packing {game_folder.name} -> {ffpfsc_path.name} (single-pass exFAT+zstd)...")
    cmd = mkpfs_cmd_base + [
        "pack", "folder",
        "--version", "PS5",
        "--inode-bits", "32",
        "--compression-level", str(compression_level),
        "--cpu-count", str(cpu_count),
        "--threshold-gain", str(threshold_gain),
    ]
    if str(block_size) != "auto":
        cmd += ["--block-size", str(block_size)]
    if temp_folder:
        cmd += ["--temp-folder", str(temp_folder)]
    if verbose:
        cmd.append("--verbose")
    if verify_enabled:
        print("[INFO] MkPFS post-build verify is ENABLED. This is slower and may use more RAM.", flush=True)
        cmd.append("--verify")
    else:
        print("[INFO] MkPFS post-build verify is disabled by default to avoid MemoryError on some systems.", flush=True)
    cmd += [str(game_folder), str(ffpfsc_path)]
    print(f"[INFO] Running: {' '.join(cmd)}", flush=True)
    try:
        subprocess.run(cmd, cwd=mkpfs_cwd, check=True)
    except subprocess.CalledProcessError as e:
        _mkpfs_error_hint(e, ffpfsc_path, game_folder)
        sys.exit(1)
    print(f"[OK] Image created: {ffpfsc_path}")


def compress_file_to_ffpfsc(
    source_file: Path,
    ffpfsc_path: Path,
    mkpfs_cmd_base: list[str],
    mkpfs_cwd: str | None,
    *,
    compression_level: int = 9,
    cpu_count: int = 0,
    threshold_gain: int = 5,
    block_size: str = "auto",
    verbose: bool = False,
    temp_folder: Path | None = None,
) -> None:
    print(f"[INFO] Compressing {source_file.name} to outer container {ffpfsc_path.name} using MkPFS...")
    cmd = mkpfs_cmd_base + [
        "pack", "file",
        "--compress",
        "--version", "PS5",
        "--inode-bits", "32",
        "--compression-level", str(compression_level),
        "--cpu-count", str(cpu_count),
        "--threshold-gain", str(threshold_gain),
    ]
    if str(block_size) != "auto":
        cmd += ["--block-size", str(block_size)]
    if temp_folder:
        cmd += ["--temp-folder", str(temp_folder)]
    if verbose:
        cmd.append("--verbose")
    cmd += [str(source_file), str(ffpfsc_path)]
    print(f"[INFO] Running: {' '.join(cmd)}", flush=True)
    try:
        subprocess.run(cmd, cwd=mkpfs_cwd, check=True)
    except subprocess.CalledProcessError as e:
        _mkpfs_error_hint(e, ffpfsc_path, source_file)
        sys.exit(1)
    print(f"[OK] Compression complete: {ffpfsc_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="PS5 FFPFSC PRO backend — create .ffpfsc containers from PS5 game folders, .exfat, or .ffpkg images."
    )
    parser.add_argument("game_folder", nargs='?', help="Source game folder, .exfat, or .ffpkg file")
    parser.add_argument("output", nargs='?', default=".", help="Output .ffpfsc file or directory")
    parser.add_argument("--keep-pfs",     action="store_true", help="Keep intermediate pfs_image.dat")
    parser.add_argument("--verify",       action="store_true", help="Run MkPFS post-build verification (slower, more RAM)")
    parser.add_argument("--batch",        action="store_true", help="Process all games/exfat files found under source")
    parser.add_argument("-f", "--force", "--overwrite", dest="overwrite", action="store_true", help="Overwrite existing files")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip a game when a .ffpfsc for its title ID is already in the output folder")
    parser.add_argument("--password",     type=str, help="Password for ZIP/RAR archives")
    # MkPFS 0.0.9 tuning flags (forwarded to mkpfs pack folder / pack file)
    parser.add_argument("--compression-level", type=int, default=9,  metavar="0-9",
                        help="Zlib compression level (0=store, 9=max, default: 9)")
    parser.add_argument("--cpu-count",    type=int, default=0,  metavar="N",
                        help="CPU cores for compression (0=auto, default: 0)")
    parser.add_argument("--threshold-gain", type=int, default=5, metavar="PCT",
                        help="Minimum per-block compression gain %% to keep compressed (default: 5)")
    parser.add_argument("--block-size",   type=str, default="auto",
                        help="PFS block size in bytes, 'auto' (65536), or 'auto-fit' (default: auto)")
    parser.add_argument("--verbose",      action="store_true", help="Verbose per-file mkpfs output")
    parser.add_argument("--temp-dir",     type=str, default=None,
                        help="Temp folder for intermediate files (default: system temp). "
                             "Use a fast NVMe drive for best performance.")

    args = parser.parse_args()

    if not args.game_folder:
        parser.print_help()
        sys.exit(1)

    game_folder = Path(args.game_folder).resolve()
    ffpfs_path  = Path(args.output).resolve()

    if not game_folder.exists():
        print(f"[ERROR] Source path does not exist: {game_folder}")
        sys.exit(1)

    # Resolve temp dir — use user-specified fast drive if provided
    user_temp: Path | None = Path(args.temp_dir).resolve() if args.temp_dir else None
    if user_temp:
        user_temp.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Using user-specified temp folder: {user_temp}", flush=True)

    _is_zip = lambda p: p.suffix.lower() == ".zip"
    _is_rar = lambda p: p.suffix.lower() in (".rar", ".r00")

    @contextlib.contextmanager
    def prepare_source_path(path: Path):
        if _is_zip(path):
            with tempfile.TemporaryDirectory(dir=user_temp) as tmpdir:
                try:
                    with zipfile.ZipFile(path) as zf:
                        for member in zf.infolist():
                            dest = Path(tmpdir) / member.filename
                            try:
                                dest.resolve().relative_to(Path(tmpdir).resolve())
                            except ValueError:
                                print(f"[ERROR] ZIP path traversal detected: {member.filename}")
                                sys.exit(1)
                        zf.extractall(tmpdir, pwd=args.password.encode() if args.password else None)
                    yield Path(tmpdir)
                except (zipfile.BadZipFile, RuntimeError) as exc:
                    print(f"[ERROR] ZIP extraction failed: {exc}")
                    sys.exit(1)
        elif _is_rar(path):
            with tempfile.TemporaryDirectory(dir=user_temp) as tmpdir:
                try:
                    from unrar import rarfile
                    with rarfile.RarFile(path, pwd=args.password) as rf:
                        rf.extractall(tmpdir)
                    yield Path(tmpdir)
                except Exception as exc:
                    print(f"[ERROR] RAR extraction failed: {exc}")
                    sys.exit(1)
        else:
            yield path

    mkpfs_cmd_base, mkpfs_cwd = _locate_mkpfs()

    # Print MkPFS version
    try:
        ver = subprocess.run(
            mkpfs_cmd_base + ["-V"],
            capture_output=True, text=True,
            cwd=mkpfs_cwd,
        )
        print(f"[INFO] MkPFS: {ver.stdout.strip() or ver.stderr.strip()}", flush=True)
    except Exception:
        pass

    # Pack options forwarded to mkpfs
    effective_cpu = max(0, args.cpu_count)

    # Auto-cap workers for large sources when the user left cpu_count at 0 (auto).
    # mkpfs spawns one worker per core; each worker buffers compressed data in RAM.
    # For files > 10 GB this easily exhausts memory on typical PCs.
    # Cap at 4 automatically — still fast, but avoids OOM crashes.
    # If the user explicitly set a cpu_count we honour it without override.
    if effective_cpu == 0:
        try:
            source_bytes = (
                game_folder.stat().st_size if game_folder.is_file()
                else sum(f.stat().st_size for f in game_folder.rglob("*") if f.is_file())
            )
            _GB = 1024 ** 3
            if source_bytes > 10 * _GB:
                import os as _os
                all_cores = _os.cpu_count() or 4
                if source_bytes > 30 * _GB:
                    # Very large game (>30 GB) — cap at 2 to avoid total RAM exhaustion
                    # even on systems with 32 GB RAM (Callisto Protocol, Days Gone, etc.)
                    cpu_auto_cap = min(2, max(1, all_cores))
                else:
                    # Large game (10–30 GB) — cap at 4
                    cpu_auto_cap = min(4, max(1, all_cores))
                print(
                    f"[INFO] Source is {source_bytes / _GB:.1f} GB — auto-capping workers "
                    f"to {cpu_auto_cap} to prevent out-of-memory crashes "
                    f"(override with the CPU cores slider).",
                    flush=True,
                )
                effective_cpu = cpu_auto_cap
        except Exception:
            pass  # stat failed — leave effective_cpu at 0 (mkpfs default)

    pack_kwargs = dict(
        compression_level=max(0, min(9, args.compression_level)),
        cpu_count=effective_cpu,
        threshold_gain=max(0, args.threshold_gain),
        block_size=args.block_size,
        verbose=args.verbose,
    )

    skipped_items: list[str] = []
    skipped_existing: list[str] = []

    with prepare_source_path(game_folder) as active_source_path:
        game_items = find_game_items(active_source_path, args.batch)

        if args.batch:
            ffpfs_path.mkdir(parents=True, exist_ok=True)
        elif not ffpfs_path.is_dir() and not ffpfs_path.suffix:
            ffpfs_path.mkdir(parents=True, exist_ok=True)

        for item in game_items:
            title_id = get_title_id(item)
            ext = ".ffpfsc"

            if args.batch or ffpfs_path.is_dir():
                current_ffpfs_path = ffpfs_path / f"{build_output_stem(item, title_id)}{ext}"
            else:
                current_ffpfs_path = ffpfs_path.with_suffix(ext)

            if args.batch:
                print(f"\n[INFO] --- Processing batch item: {title_id} ({item.name}) ---")

            # Already compressed? Don't spend hours redoing it.
            already = find_existing_outputs(current_ffpfs_path.parent, title_id)
            if already and args.skip_existing:
                print(
                    f"[SKIP] {item.name} is already compressed.\n"
                    f"[SKIP]   Existing output: {already[0]}\n"
                    f"[SKIP]   Turn off 'Skip already compressed games' to rebuild it.",
                    flush=True,
                )
                skipped_existing.append(title_id)
                continue

            if current_ffpfs_path.exists():
                if args.overwrite:
                    print(f"[WARN] Output file already exists. Overwriting: {current_ffpfs_path}")
                    try:
                        current_ffpfs_path.unlink()
                    except Exception as e:
                        print(f"[ERROR] Failed to remove existing output file: {e}")
                        sys.exit(1)
                else:
                    print(f"[WARN] Output file already exists: {current_ffpfs_path}")
                    try:
                        if sys.stdin.isatty():
                            response = input("Overwrite existing file? [y/N]: ").strip().lower()
                        else:
                            print("[INFO] Non-interactive shell — skipping overwrite.")
                            response = 'n'
                    except (KeyboardInterrupt, EOFError):
                        print("\n[INFO] Cancelled.")
                        sys.exit(0)
                    if response not in ('y', 'yes'):
                        print(f"[INFO] Skipping: {current_ffpfs_path.name}")
                        continue
                    try:
                        current_ffpfs_path.unlink()
                    except Exception as e:
                        print(f"[ERROR] Failed to remove existing output file: {e}")
                        sys.exit(1)

            # Fail fast on a destination that cannot hold the result, instead of
            # letting mkpfs abort after the whole setup has already run.
            blockers = preflight_output_checks(item, current_ffpfs_path)
            if blockers:
                print(f"[ERROR] Cannot write {current_ffpfs_path.name} to {current_ffpfs_path.parent}", flush=True)
                for reason in blockers:
                    print(f"[ERROR] {reason}", flush=True)
                if args.batch:
                    print(f"[WARN] Skipping batch item: {title_id}", flush=True)
                    skipped_items.append(title_id)
                    continue
                sys.exit(1)

            if item.is_file() and item.suffix.lower() in ('.exfat', '.ffpkg'):
                # Direct disk image (.exfat / .ffpkg) -> .ffpfsc (single-file streaming path)
                compress_file_to_ffpfsc(
                    item, current_ffpfs_path, mkpfs_cmd_base, mkpfs_cwd,
                    temp_folder=user_temp,
                    **pack_kwargs,
                )
            else:
                # Game folder: single-pass exFAT → .ffpfsc (mkpfs 0.0.9+)
                # --keep-pfs is silently ignored for folder sources (no intermediate file)
                pack_folder_single_pass(
                    item, current_ffpfs_path, mkpfs_cmd_base, mkpfs_cwd,
                    verify_enabled=args.verify,
                    temp_folder=user_temp,
                    **pack_kwargs,
                )

    if skipped_existing:
        print(
            f"\n[INFO] {len(skipped_existing)} game(s) were already compressed and were skipped: "
            f"{', '.join(skipped_existing)}"
        )

    if skipped_items:
        print(
            f"\n[ERROR] {len(skipped_items)} batch item(s) were skipped because the output "
            f"destination could not hold them: {', '.join(skipped_items)}"
        )
        sys.exit(1)

    print("\n[SUCCESS] All operations completed successfully!")


if __name__ == "__main__":
    main()
