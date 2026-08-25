# also u can be happy about fallbacks old one was like this lol:
#find_so()
#replace_bytes()
#¯\_(ツ)_/¯

#no game files are included. The tool talks to an already connected android
#device through adb verifies the installed ARMv7 libil2cpp.so, and asks the
#devices su implementation to overwrite that extracted library in place.
"""
Forza Customs ADB Patcher
"""

#Imports here dawg
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

#varis go here M
APP_TITLE = "Forza Customs ADB Patcher"
GAME_PACKAGE = "com.hutchgames.ccw"
GAME_ACTIVITY = "com.unity3d.player.UnityPlayerActivity"
EXPECTED_SIZE = 63_342_500
PATCH_OFFSET = 0x12B74A8
ORIGINAL_BYTES = bytes.fromhex("00 10 A0 E1")
PATCHED_BYTES = bytes.fromhex("00 10 A0 E3")
ORIGINAL_SHA256 = "60b21e2496852bb99d14377aa221a8a40a2b56ac7641c6d43ff4ffafbdf5909c"
PATCHED_SHA256 = "df16cadd7fc5e31e61561aed8fbc8ed79adbcbeb50b9b71af509b6a804686e6f"
REMOTE_TEMP = "/data/local/tmp/forza-customs-libil2cpp.patched.so"

class ToolError(RuntimeError):
    pass

#should fail
def creation_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0

#may vary dunno 2 devices had diff ones
def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"

# File verification / local patching
def sha256_file(path: Path) -> str:
    file_hashy = hashlib.sha256()
    with path.open("rb") as sauce_path:
        while block := sauce_path.read(256 * 1024):
            file_hashy.update(block)
    return file_hashy.hexdigest()

def classify(path: Path) -> tuple[str, str]:
    size = path.stat().st_size
    file_hashy = sha256_file(path)
    if size == EXPECTED_SIZE and file_hashy == ORIGINAL_SHA256:
        return "original", file_hashy
    if size == EXPECTED_SIZE and file_hashy == PATCHED_SHA256:
        return "patched", file_hashy
    return "unsupported", file_hashy

def create_patched_copy(original: Path, output_path: Path) -> None:
    lib_state, file_hashy = classify(original)
    if lib_state != "original":
        raise ToolError(f"Refusing to patch {lib_state} library ({file_hashy})")

    shutil.copyfile(original, output_path)

    with output_path.open("r+b") as lib_file:
        lib_file.seek(PATCH_OFFSET)
        found = lib_file.read(4)

        if found != ORIGINAL_BYTES:
            raise ToolError(
                f"Bytes at 0x{PATCH_OFFSET:X} are {found.hex(' ')}, "
                f"expected {ORIGINAL_BYTES.hex(' ')}"
            )

        lib_file.seek(PATCH_OFFSET)
        lib_file.write(PATCHED_BYTES)
        lib_file.flush()
        os.fsync(lib_file.fileno())

    lib_state, file_hashy = classify(output_path)
    if lib_state != "patched":
        raise ToolError(f"Local post-patch verification failed ({file_hashy})")

# ADB setup
def find_adb() -> str:
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "adb.exe",
        script_dir / "platform-tools" / "adb.exe",
        Path.cwd() / "adb.exe",
        Path.cwd() / "platform-tools" / "adb.exe",
    ]

    for variable in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "platform-tools" / "adb.exe")

    located = shutil.which("adb") or shutil.which("adb.exe")
    if located:
        candidates.append(Path(located))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return ""

def backup_root() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "ForzaCustomsADBPatcher" / "backups"
    return Path.home() / ".forza-customs-adb-patcher" / "backups"

class AdbClient:
    def __init__(self, adb: str, device_serialnum: str | None = None) -> None:
        path = Path(adb.strip().strip('"'))

        if not path.is_file():
            raise ToolError(
                "adb.exe was not found. Select it from Android platform-tools."
            )

        self.adb = str(path)
        self.device_serialnum = device_serialnum

    def _base(self) -> list[str]:
        command = [self.adb]

        if self.device_serialnum:
            command += ["-s", self.device_serialnum]

        return command

    def run(
        self,
        arguments: list[str],
        *,
        timeout: int = 120,
        binary: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                self._base() + arguments,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=not binary,
                timeout=timeout,
                creationflags=creation_flags(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                f"ADB timed out while running: {' '.join(arguments[:2])}"
            ) from exc
        except OSError as exc:
            raise ToolError(f"Could not start adb.exe: {exc}") from exc

        if check and result.returncode != 0:
            stderr = (
                result.stderr
                if not binary
                else result.stderr.decode(errors="replace")
            )
            stdout = result.stdout if not binary else b""
            detail = (stderr or stdout or "unknown ADB error").strip()

            raise ToolError(
                f"ADB failed ({result.returncode}): {detail}"
            )

        return result

    def devices(self) -> tuple[list[str], list[str]]:
        result = self.run(["devices"], timeout=30)
        devices = []
        device_errs = []

        for line in result.stdout.splitlines()[1:]:
            line = line.strip()

            if not line:
                continue

            parts = line.split()

            if len(parts) < 2:
                continue

            device_serialnum, lib_state = parts[0], parts[1]

            if lib_state == "device":
                devices.append(device_serialnum)
            else:
                device_errs.append(
                    f"{device_serialnum}: {lib_state}"
                )

        return devices, device_errs

    def root_shell(self, command: str, *, timeout: int = 120) -> str:
        remote = "su -c " + shell_quote(command)
        result = self.run(["shell", remote], timeout=timeout)
        return result.stdout.strip()

    def ensure_root(self) -> str:
        root_dntty = self.root_shell("id", timeout=45)

        if "uid=0" not in root_dntty:
            raise ToolError(
                f"Root was not granted. Device returned: "
                f"{root_dntty or '(empty)'}"
            )

        return root_dntty

    def find_library(self) -> str:
        package_paths = self.root_shell(
            f"pm path {GAME_PACKAGE}"
        )

        install_dir = ""

        for line in package_paths.splitlines():
            line = line.strip()

            if line.startswith("package:") and line.endswith("/base.apk"):
                install_dir = line[len("package:"):-len("/base.apk")]
                break

        if not install_dir:
            raise ToolError(
                "Forza Customs is not installed, or base.apk was not found."
            )

        output_path = self.root_shell(
            f"find {shell_quote(install_dir + '/lib')} -type f "
            "-name libil2cpp.so -print 2>/dev/null"
        )

        lib_paths = [
            line.strip()
            for line in output_path.splitlines()
            if line.strip().startswith(install_dir + "/lib/")
        ]

        if len(lib_paths) != 1:
            raise ToolError(
                f"Expected one installed libil2cpp.so, found {len(lib_paths)}."
            )

        return lib_paths[0]

    def copy_from_root(
        self,
        remote_path: str,
        local_path: Path,
    ) -> None:
        remote = "su -c " + shell_quote(
            f"cat {shell_quote(remote_path)}"
        )

        try:
            with local_path.open("wb") as output_path:
                result = subprocess.run(
                    self._base() + ["exec-out", remote],
                    stdout=output_path,
                    stderr=subprocess.PIPE,
                    timeout=180,
                    creationflags=creation_flags(),
                )
        except subprocess.TimeoutExpired as exc:
            local_path.unlink(missing_ok=True)
            raise ToolError(
                "Timed out while copying the installed library."
            ) from exc
        except OSError as exc:
            local_path.unlink(missing_ok=True)
            raise ToolError(
                f"Could not copy the installed library: {exc}"
            ) from exc

        if result.returncode != 0:
            local_path.unlink(missing_ok=True)
            detail = result.stderr.decode(errors="replace").strip()

            raise ToolError(
                f"Reading installed library failed: "
                f"{detail or 'unknown error'}"
            )

    def push(self, local_path: Path, remote_path: str) -> None:
        self.run(
            ["push", str(local_path), remote_path],
            timeout=180,
        )

    def overwrite_library(
        self,
        local_path: Path,
        lib_path: str,
    ) -> None:
        self.push(local_path, REMOTE_TEMP)

        try:
            self.root_shell(
                f"am force-stop {GAME_PACKAGE}"
            )

            command = (
                f"[ -f {shell_quote(lib_path)} ] || exit 23; "
                f"cat {shell_quote(REMOTE_TEMP)} > "
                f"{shell_quote(lib_path)} && "
                f"chmod 755 {shell_quote(lib_path)} && sync"
            )

            self.root_shell(command, timeout=180)

        finally:
            try:
                self.root_shell(
                    f"rm -f {shell_quote(REMOTE_TEMP)}",
                    timeout=30,
                )
            except ToolError:
                pass

    def launch_game(self) -> str:
        component = f"{GAME_PACKAGE}/{GAME_ACTIVITY}"

        result = self.run(
            ["shell", "am", "start", "-n", component],
            timeout=45,
        )

        return result.stdout.strip()

class PatchService:
    def __init__(
        self,
        adb: str,
        device_serialnum: str,
    ) -> None:
        self.device_serialnum = device_serialnum
        self.adb = AdbClient(adb, device_serialnum)

    @property
    def backup_path(self) -> Path:
        safe_serial = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            self.device_serialnum,
        )

        return (
            backup_root()
            / safe_serial
            / "libil2cpp-v7.0.14670-original.so"
        )

    def snapshot(
        self,
        lib_path: str,
        directory: Path,
        name: str,
    ) -> Path:
        output_path = directory / name
        self.adb.copy_from_root(lib_path, output_path)
        return output_path

    def check(self) -> str:
        root_dntty = self.adb.ensure_root()
        lib_path = self.adb.find_library()

        with tempfile.TemporaryDirectory(
            prefix="forza-adb-check-"
        ) as temp_dir:
            current_lib = self.snapshot(
                lib_path,
                Path(temp_dir),
                "installed.so",
            )

            lib_state, file_hashy = classify(current_lib)
            size = current_lib.stat().st_size

        backup_state = "not created"

        if self.backup_path.is_file():
            backup_state, _ = classify(self.backup_path)

        return (
            f"Root: {root_dntty}\n"
            f"Device: {self.device_serialnum}\n"
            f"Target: {lib_path}\n"
            f"Size: {size:,} bytes\n"
            f"SHA-256: {file_hashy}\n"
            f"State: {lib_state}\n"
            f"PC backup: {backup_state}\n"
            f"Backup path: {self.backup_path}"
        )

    def _save_backup(self, sauce_path: Path) -> None:
        if self.backup_path.exists():
            lib_state, file_hashy = classify(
                self.backup_path
            )

            if lib_state != "original":
                raise ToolError(
                    f"Existing backup is invalid ({file_hashy}). "
                    "Refusing to replace it."
                )

            return

        self.backup_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_dir = self.backup_path.with_suffix(".tmp")
        temp_dir.unlink(missing_ok=True)

        shutil.copyfile(sauce_path, temp_dir)

        lib_state, file_hashy = classify(temp_dir)

        if lib_state != "original":
            temp_dir.unlink(missing_ok=True)

            raise ToolError(
                f"New backup failed verification ({file_hashy})."
            )

        os.replace(temp_dir, self.backup_path)

    def apply(self) -> str:
        self.adb.ensure_root()
        lib_path = self.adb.find_library()

        with tempfile.TemporaryDirectory(
            prefix="forza-adb-apply-"
        ) as temp_dir:
            temp_dir = Path(temp_dir)

            current_lib = self.snapshot(
                lib_path,
                temp_dir,
                "installed-original.so",
            )

            lib_state, file_hashy = classify(current_lib)

            if lib_state == "patched":
                return (
                    "Already patched and verified.\n"
                    f"Target: {lib_path}\n"
                    f"SHA-256: {file_hashy}"
                )

            if lib_state != "original":
                raise ToolError(
                    "Unsupported installed library. "
                    "No write was attempted.\n"
                    f"Size: {current_lib.stat().st_size:,}\n"
                    f"SHA-256: {file_hashy}"
                )

            self._save_backup(current_lib)

            patched_lib = temp_dir / "libil2cpp-patched.so"
            create_patched_copy(
                current_lib,
                patched_lib,
            )

            write_attempted = False

            try:
                write_attempted = True

                self.adb.overwrite_library(
                    patched_lib,
                    lib_path,
                )

                ok_lib = self.snapshot(
                    lib_path,
                    temp_dir,
                    "installed-verify.so",
                )

                final_state, final_hash = classify(ok_lib)

                if final_state != "patched":
                    raise ToolError(
                        "Installed post-write verification failed "
                        f"({final_hash})."
                    )

            except Exception as failure:
                if write_attempted and self.backup_path.is_file():
                    try:
                        backup_state, _ = classify(
                            self.backup_path
                        )

                        if backup_state == "original":
                            self.adb.overwrite_library(
                                self.backup_path,
                                lib_path,
                            )

                            raise ToolError(
                                f"Patch failed: {failure}\n\n"
                                "The verified original was restored automatically."
                            ) from failure

                    except ToolError as rollback_error:
                        if rollback_error.__cause__ is failure:
                            raise rollback_error

                        raise ToolError(
                            f"Patch failed: {failure}\n"
                            f"Automatic rollback also failed: "
                            f"{rollback_error}\n"
                            "Reinstall the original split before launching."
                        ) from failure

                raise

        return (
            "PATCH APPLIED AND VERIFIED\n"
            f"Device: {self.device_serialnum}\n"
            f"Target: {lib_path}\n"
            f"SHA-256: {PATCHED_SHA256}\n"
            f"Original backup: {self.backup_path}"
        )

    def restore(self) -> str:
        self.adb.ensure_root()

        if not self.backup_path.is_file():
            raise ToolError(
                f"No PC backup exists for {self.device_serialnum}."
            )

        backup_state, backup_hash = classify(
            self.backup_path
        )

        if backup_state != "original":
            raise ToolError(
                f"PC backup is invalid ({backup_hash})."
            )

        lib_path = self.adb.find_library()

        with tempfile.TemporaryDirectory(
            prefix="forza-adb-restore-"
        ) as temp_dir:
            temp_dir = Path(temp_dir)

            current_lib = self.snapshot(
                lib_path,
                temp_dir,
                "installed-current.so",
            )

            current_state, current_hash = classify(
                current_lib
            )

            if current_state == "original":
                return (
                    "Already original and verified.\n"
                    f"Target: {lib_path}"
                )

            if current_state != "patched":
                raise ToolError(
                    f"Installed library is unsupported "
                    f"({current_hash}). "
                    "Refusing to overwrite it."
                )

            self.adb.overwrite_library(
                self.backup_path,
                lib_path,
            )

            ok_lib = self.snapshot(
                lib_path,
                temp_dir,
                "installed-verify.so",
            )

            final_state, final_hash = classify(ok_lib)

            if final_state != "original":
                raise ToolError(
                    f"Restore verification failed ({final_hash})."
                )

        return (
            "ORIGINAL RESTORED AND VERIFIED\n"
            f"Device: {self.device_serialnum}\n"
            f"Target: {lib_path}\n"
            f"SHA-256: {ORIGINAL_SHA256}"
        )

class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("820x570")
        self.root.minsize(720, 500)

        self.adb = tk.StringVar(value=find_adb())
        self.device_serialnum = tk.StringVar()
        self.status = tk.StringVar(
            value="Select adb.exe, then refresh devices."
        )

        self.busy = False
        self.buttons: list[ttk.Button] = []

        main_frame = ttk.Frame(root, padding=16)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(
            main_frame,
            text=APP_TITLE,
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            main_frame,
            text="For Forza Customs v7.0.14670 ARMv7 only — Android root is required.",
        ).pack(anchor="w", pady=(2, 14))

        adb_frame = ttk.Frame(main_frame)
        adb_frame.pack(fill="x")

        ttk.Label(
            adb_frame,
            text="adb.exe:",
            width=11,
        ).pack(side="left")

        ttk.Entry(
            adb_frame,
            textvariable=self.adb,
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            adb_frame,
            text="Browse…",
            command=self.browse_adb,
        ).pack(side="left", padx=(8, 0))

        device_frame = ttk.Frame(main_frame)
        device_frame.pack(fill="x", pady=(10, 0))

        ttk.Label(
            device_frame,
            text="Device:",
            width=11,
        ).pack(side="left")

        self.device_box = ttk.Combobox(
            device_frame,
            textvariable=self.device_serialnum,
            state="readonly",
        )

        self.device_box.pack(
            side="left",
            fill="x",
            expand=True,
        )

        refresh_button = ttk.Button(
            device_frame,
            text="Refresh",
            command=self.refresh_devices,
        )

        refresh_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.buttons.append(refresh_button)

        action_frame = ttk.Frame(main_frame)
        action_frame.pack(
            fill="x",
            pady=(14, 10),
        )

        for label, command in (
            ("Check", self.check),
            ("Apply patch", self.confirm_apply),
            ("Restore original", self.confirm_restore),
            ("Launch game", self.launch),
            ("Open backups", self.open_backups),
        ):
            button = ttk.Button(
                action_frame,
                text=label,
                command=command,
            )

            button.pack(
                side="left",
                padx=(0, 8),
            )

            self.buttons.append(button)

        ttk.Separator(main_frame).pack(
            fill="x",
            pady=(0, 10),
        )

        ttk.Label(
            main_frame,
            textvariable=self.status,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        log_frame = ttk.Frame(main_frame)
        log_frame.pack(
            fill="both",
            expand=True,
            pady=(8, 0),
        )

        self.log = tk.Text(
            log_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )

        scrollbar = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log.yview,
        )

        self.log.configure(
            yscrollcommand=scrollbar.set
        )

        self.log.pack(
            side="left",
            fill="both",
            expand=True,
        )

        scrollbar.pack(
            side="right",
            fill="y",
        )

        ttk.Label(
            main_frame,
            text="No APK is rebuilt or resigned. Unknown library hashes are never written.",
        ).pack(
            anchor="w",
            pady=(10, 0),
        )

        if self.adb.get():
            self.root.after(
                150,
                self.refresh_devices,
            )

    def append_log(
        self,
        message: str,
        *,
        clear: bool = False,
    ) -> None:
        self.log.configure(state="normal")

        if clear:
            self.log.delete("1.0", "end")

        self.log.insert(
            "end",
            message.rstrip() + "\n",
        )

        self.log.see("end")
        self.log.configure(state="disabled")

    def set_busy(
        self,
        busy: bool,
        status: str,
    ) -> None:
        self.busy = busy
        self.status.set(status)

        for button in self.buttons:
            button.configure(
                state="disabled" if busy else "normal"
            )

    def browse_adb(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select adb.exe",
            filetypes=[
                ("Android Debug Bridge", "adb.exe"),
                ("All files", "*.*"),
            ],
        )

        if selected:
            self.adb.set(selected)
            self.refresh_devices()

    def refresh_devices(self) -> None:
        adb = self.adb.get()

        def work() -> str:
            client = AdbClient(adb)
            devices, device_errs = client.devices()

            self.root.after(
                0,
                lambda: self.set_device_list(devices),
            )

            details = [
                f"Ready devices: {len(devices)}"
            ]

            details.extend(device_errs)

            if not devices:
                details.append(
                    "Connect USB ADB or run: adb connect PHONE_IP:PORT"
                )

            return "\n".join(details)

        self.run_async(
            "Refreshing devices…",
            work,
        )

    def set_device_list(
        self,
        devices: list[str],
    ) -> None:
        previous = self.device_serialnum.get()
        self.device_box["values"] = devices

        if previous in devices:
            self.device_serialnum.set(previous)
        elif devices:
            self.device_serialnum.set(devices[0])
        else:
            self.device_serialnum.set("")

    def service(self) -> PatchService:
        device_serialnum = self.device_serialnum.get().strip()

        if not device_serialnum:
            raise ToolError(
                "No ready ADB device is selected."
            )

        return PatchService(
            self.adb.get(),
            device_serialnum,
        )

    def check(self) -> None:
        self.run_service_async(
            "Checking root and installed game…",
            lambda service: service.check(),
        )

    def confirm_apply(self) -> None:
        if messagebox.askyesno(
            "Apply patch?",
            "The game will be force-stopped. The exact original library "
            "will be backed up to this PC and the installed extracted "
            "copy will be patched through root.\n\n"
            "Continue?",
        ):
            self.run_service_async(
                "Applying and verifying patch…",
                lambda service: service.apply(),
            )

    def confirm_restore(self) -> None:
        if messagebox.askyesno(
            "Restore original?",
            "The game will be force-stopped and the verified PC backup "
            "will replace the supported patched library.\n\n"
            "Continue?",
        ):
            self.run_service_async(
                "Restoring and verifying original…",
                lambda service: service.restore(),
            )

    def launch(self) -> None:
        def work(service: PatchService) -> str:
            output_path = service.adb.launch_game()
            return "Game launch requested.\n" + output_path

        self.run_service_async(
            "Launching game…",
            work,
        )

    def open_backups(self) -> None:
        backup_dir = backup_root()
        backup_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            if os.name == "nt":
                os.startfile(backup_dir)  # typee ignore[attr-defined]
            else:
                subprocess.Popen(
                    ["xdg-open", str(backup_dir)]
                )
        except OSError as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Could not open {backup_dir}: {exc}",
            )

    def run_async(
        self,
        activity: str,
        operation: Callable[[], str],
    ) -> None:
        if self.busy:
            return

        self.set_busy(
            True,
            activity,
        )

        self.append_log(
            activity,
            clear=True,
        )

        def worker() -> None:
            try:
                result = operation()
            except Exception as exc:
                self.root.after(
                    0,
                    lambda: self.finish_error(
                        str(exc) or type(exc).__name__
                    ),
                )
            else:
                self.root.after(
                    0,
                    lambda: self.finish_success(result),
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def run_service_async(
        self,
        activity: str,
        operation: Callable[[PatchService], str],
    ) -> None:
        # Capture Tk vari on UI befr startin background I/O.
        try:
            service = self.service()
        except Exception as exc:
            self.finish_error(
                str(exc) or type(exc).__name__
            )
            return

        self.run_async(
            activity,
            lambda: operation(service),
        )

    def finish_success(
        self,
        result: str,
    ) -> None:
        self.append_log(
            "\n" + result
        )

        self.set_busy(
            False,
            "Ready",
        )

    def finish_error(
        self,
        error: str,
    ) -> None:
        self.append_log(
            "\nERROR\n" + error
        )

        self.set_busy(
            False,
            "Operation failed",
        )

        messagebox.showerror(
            APP_TITLE,
            error,
        )

def main() -> int:
    root = tk.Tk()

    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass

    MainWindow(root)
    root.mainloop()

    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#apks all on u m i aint doin allat
#cuz figuring this out was hell
#ima slime the guy who didint patch this out for a last update when i see em