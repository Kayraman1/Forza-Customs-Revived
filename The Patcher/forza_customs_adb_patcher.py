#!/usr/bin/env python3
"""small Windows GUI for the Forza Customs v7.0.14670 ADB patch.

No game files are included. The tool talks to an already connected Android
device through adb verifies the installed ARMv7 libil2cpp.so, and asks the
devices su implementation to overwrite that extracted library in place.
"""

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
    """Expected fail"""


def creation_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


def shell_quote(value: str) -> str:
    """Quote value for Androids /system/bin/sh."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(256 * 1024):
            digest.update(block)
    return digest.hexdigest()


def classify(path: Path) -> tuple[str, str]:
    size = path.stat().st_size
    digest = sha256_file(path)
    if size == EXPECTED_SIZE and digest == ORIGINAL_SHA256:
        return "original", digest
    if size == EXPECTED_SIZE and digest == PATCHED_SHA256:
        return "patched", digest
    return "unsupported", digest


def create_patched_copy(original: Path, output: Path) -> None:
    state, digest = classify(original)
    if state != "original":
        raise ToolError(f"Refusing to patch {state} library ({digest})")

    shutil.copyfile(original, output)
    with output.open("r+b") as target:
        target.seek(PATCH_OFFSET)
        found = target.read(4)
        if found != ORIGINAL_BYTES:
            raise ToolError(
                f"Bytes at 0x{PATCH_OFFSET:X} are {found.hex(' ')}, "
                f"expected {ORIGINAL_BYTES.hex(' ')}"
            )
        target.seek(PATCH_OFFSET)
        target.write(PATCHED_BYTES)
        target.flush()
        os.fsync(target.fileno())

    state, digest = classify(output)
    if state != "patched":
        raise ToolError(f"Local post-patch verification failed ({digest})")


def find_adb() -> str:
    script_dir = Path(__file__).resolve().parent
    candidates: list[Path] = [
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
    def __init__(self, adb_path: str, serial: str | None = None) -> None:
        path = Path(adb_path.strip().strip('"'))
        if not path.is_file():
            raise ToolError("adb.exe was not found. Select it from Android platform-tools.")
        self.adb = str(path)
        self.serial = serial

    def _base(self) -> list[str]:
        command = [self.adb]
        if self.serial:
            command += ["-s", self.serial]
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
            raise ToolError(f"ADB timed out while running: {' '.join(arguments[:2])}") from exc
        except OSError as exc:
            raise ToolError(f"Could not start adb.exe: {exc}") from exc

        if check and result.returncode != 0:
            error = result.stderr if not binary else result.stderr.decode(errors="replace")
            normal = result.stdout if not binary else b""
            detail = (error or normal or "unknown ADB error").strip()
            raise ToolError(f"ADB failed ({result.returncode}): {detail}")
        return result

    def devices(self) -> tuple[list[str], list[str]]:
        result = self.run(["devices"], timeout=30)
        ready: list[str] = []
        problems: list[str] = []
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            if state == "device":
                ready.append(serial)
            else:
                problems.append(f"{serial}: {state}")
        return ready, problems

    def root_shell(self, command: str, *, timeout: int = 120) -> str:
        remote = "su -c " + shell_quote(command)
        result = self.run(["shell", remote], timeout=timeout)
        return result.stdout.strip()

    def ensure_root(self) -> str:
        identity = self.root_shell("id", timeout=45)
        if "uid=0" not in identity:
            raise ToolError(f"Root was not granted. Device returned: {identity or '(empty)'}")
        return identity

    def find_library(self) -> str:
        package_paths = self.root_shell(f"pm path {GAME_PACKAGE}")
        install_dir = ""
        for line in package_paths.splitlines():
            line = line.strip()
            if line.startswith("package:") and line.endswith("/base.apk"):
                install_dir = line[len("package:") : -len("/base.apk")]
                break
        if not install_dir:
            raise ToolError("Forza Customs is not installed, or base.apk was not found.")

        output = self.root_shell(
            f"find {shell_quote(install_dir + '/lib')} -type f "
            "-name libil2cpp.so -print 2>/dev/null"
        )
        matches = [
            line.strip()
            for line in output.splitlines()
            if line.strip().startswith(install_dir + "/lib/")
        ]
        if len(matches) != 1:
            raise ToolError(f"Expected one installed libil2cpp.so, found {len(matches)}.")
        return matches[0]

    def copy_from_root(self, remote_path: str, local_path: Path) -> None:
        remote = "su -c " + shell_quote(f"cat {shell_quote(remote_path)}")
        try:
            with local_path.open("wb") as output:
                result = subprocess.run(
                    self._base() + ["exec-out", remote],
                    stdout=output,
                    stderr=subprocess.PIPE,
                    timeout=180,
                    creationflags=creation_flags(),
                )
        except subprocess.TimeoutExpired as exc:
            local_path.unlink(missing_ok=True)
            raise ToolError("Timed out while copying the installed library.") from exc
        except OSError as exc:
            local_path.unlink(missing_ok=True)
            raise ToolError(f"Could not copy the installed library: {exc}") from exc

        if result.returncode != 0:
            local_path.unlink(missing_ok=True)
            detail = result.stderr.decode(errors="replace").strip()
            raise ToolError(f"Reading installed library failed: {detail or 'unknown error'}")

    def push(self, local_path: Path, remote_path: str) -> None:
        self.run(["push", str(local_path), remote_path], timeout=180)

    def overwrite_library(self, local_path: Path, target: str) -> None:
        self.push(local_path, REMOTE_TEMP)
        try:
            self.root_shell(f"am force-stop {GAME_PACKAGE}")
            command = (
                f"[ -f {shell_quote(target)} ] || exit 23; "
                f"cat {shell_quote(REMOTE_TEMP)} > {shell_quote(target)} && "
                f"chmod 755 {shell_quote(target)} && sync"
            )
            self.root_shell(command, timeout=180)
        finally:
            try:
                self.root_shell(f"rm -f {shell_quote(REMOTE_TEMP)}", timeout=30)
            except ToolError:
                pass

    def launch_game(self) -> str:
        component = f"{GAME_PACKAGE}/{GAME_ACTIVITY}"
        result = self.run(["shell", "am", "start", "-n", component], timeout=45)
        return result.stdout.strip()


class PatchService:
    def __init__(self, adb_path: str, serial: str) -> None:
        self.serial = serial
        self.adb = AdbClient(adb_path, serial)

    @property
    def backup_path(self) -> Path:
        safe_serial = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.serial)
        return backup_root() / safe_serial / "libil2cpp-v7.0.14670-original.so"

    def snapshot(self, target: str, directory: Path, name: str) -> Path:
        output = directory / name
        self.adb.copy_from_root(target, output)
        return output

    def check(self) -> str:
        identity = self.adb.ensure_root()
        target = self.adb.find_library()
        with tempfile.TemporaryDirectory(prefix="forza-adb-check-") as temporary:
            current = self.snapshot(target, Path(temporary), "installed.so")
            state, digest = classify(current)
            size = current.stat().st_size

        backup_state = "not created"
        if self.backup_path.is_file():
            backup_state, _ = classify(self.backup_path)
        return (
            f"Root: {identity}\n"
            f"Device: {self.serial}\n"
            f"Target: {target}\n"
            f"Size: {size:,} bytes\n"
            f"SHA-256: {digest}\n"
            f"State: {state}\n"
            f"PC backup: {backup_state}\n"
            f"Backup path: {self.backup_path}"
        )

    def _save_backup(self, source: Path) -> None:
        if self.backup_path.exists():
            state, digest = classify(self.backup_path)
            if state != "original":
                raise ToolError(f"Existing backup is invalid ({digest}). Refusing to replace it.")
            return

        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.backup_path.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        shutil.copyfile(source, temporary)
        state, digest = classify(temporary)
        if state != "original":
            temporary.unlink(missing_ok=True)
            raise ToolError(f"New backup failed verification ({digest}).")
        os.replace(temporary, self.backup_path)

    def apply(self) -> str:
        self.adb.ensure_root()
        target = self.adb.find_library()
        with tempfile.TemporaryDirectory(prefix="forza-adb-apply-") as temporary:
            folder = Path(temporary)
            current = self.snapshot(target, folder, "installed-original.so")
            state, digest = classify(current)
            if state == "patched":
                return f"Already patched and verified.\nTarget: {target}\nSHA-256: {digest}"
            if state != "original":
                raise ToolError(
                    f"Unsupported installed library. No write was attempted.\n"
                    f"Size: {current.stat().st_size:,}\nSHA-256: {digest}"
                )

            self._save_backup(current)
            patched = folder / "libil2cpp-patched.so"
            create_patched_copy(current, patched)
            write_attempted = False
            try:
                write_attempted = True
                self.adb.overwrite_library(patched, target)
                verified = self.snapshot(target, folder, "installed-verify.so")
                final_state, final_digest = classify(verified)
                if final_state != "patched":
                    raise ToolError(f"Installed post-write verification failed ({final_digest}).")
            except Exception as failure:
                if write_attempted and self.backup_path.is_file():
                    try:
                        backup_state, _ = classify(self.backup_path)
                        if backup_state == "original":
                            self.adb.overwrite_library(self.backup_path, target)
                            raise ToolError(
                                f"Patch failed: {failure}\n\n"
                                "The verified original was restored automatically."
                            ) from failure
                    except ToolError as rollback_error:
                        if rollback_error.__cause__ is failure:
                            raise rollback_error
                        raise ToolError(
                            f"Patch failed: {failure}\nAutomatic rollback also failed: "
                            f"{rollback_error}\nReinstall the original split before launching."
                        ) from failure
                raise

        return (
            "PATCH APPLIED AND VERIFIED\n"
            f"Device: {self.serial}\n"
            f"Target: {target}\n"
            f"SHA-256: {PATCHED_SHA256}\n"
            f"Original backup: {self.backup_path}"
        )

    def restore(self) -> str:
        self.adb.ensure_root()
        if not self.backup_path.is_file():
            raise ToolError(f"No PC backup exists for {self.serial}.")
        backup_state, backup_digest = classify(self.backup_path)
        if backup_state != "original":
            raise ToolError(f"PC backup is invalid ({backup_digest}).")

        target = self.adb.find_library()
        with tempfile.TemporaryDirectory(prefix="forza-adb-restore-") as temporary:
            folder = Path(temporary)
            current = self.snapshot(target, folder, "installed-current.so")
            current_state, current_digest = classify(current)
            if current_state == "original":
                return f"Already original and verified.\nTarget: {target}"
            if current_state != "patched":
                raise ToolError(
                    f"Installed library is unsupported ({current_digest}). Refusing to overwrite it."
                )

            self.adb.overwrite_library(self.backup_path, target)
            verified = self.snapshot(target, folder, "installed-verify.so")
            final_state, final_digest = classify(verified)
            if final_state != "original":
                raise ToolError(f"Restore verification failed ({final_digest}).")

        return (
            "ORIGINAL RESTORED AND VERIFIED\n"
            f"Device: {self.serial}\n"
            f"Target: {target}\n"
            f"SHA-256: {ORIGINAL_SHA256}"
        )


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("820x570")
        self.root.minsize(720, 500)

        self.adb_path = tk.StringVar(value=find_adb())
        self.device = tk.StringVar()
        self.status = tk.StringVar(value="Select adb.exe, then refresh devices.")
        self.busy = False
        self.buttons: list[ttk.Button] = []

        outer = ttk.Frame(root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=APP_TITLE, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="For Forza Customs v7.0.14670 ARMv7 only — Android root is required.",
        ).pack(anchor="w", pady=(2, 14))

        adb_row = ttk.Frame(outer)
        adb_row.pack(fill="x")
        ttk.Label(adb_row, text="adb.exe:", width=11).pack(side="left")
        ttk.Entry(adb_row, textvariable=self.adb_path).pack(side="left", fill="x", expand=True)
        ttk.Button(adb_row, text="Browse…", command=self.browse_adb).pack(side="left", padx=(8, 0))

        device_row = ttk.Frame(outer)
        device_row.pack(fill="x", pady=(10, 0))
        ttk.Label(device_row, text="Device:", width=11).pack(side="left")
        self.device_box = ttk.Combobox(device_row, textvariable=self.device, state="readonly")
        self.device_box.pack(side="left", fill="x", expand=True)
        refresh = ttk.Button(device_row, text="Refresh", command=self.refresh_devices)
        refresh.pack(side="left", padx=(8, 0))
        self.buttons.append(refresh)

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(14, 10))
        for label, command in (
            ("Check", self.check),
            ("Apply patch", self.confirm_apply),
            ("Restore original", self.confirm_restore),
            ("Launch game", self.launch),
            ("Open backups", self.open_backups),
        ):
            button = ttk.Button(actions, text=label, command=command)
            button.pack(side="left", padx=(0, 8))
            self.buttons.append(button)

        ttk.Separator(outer).pack(fill="x", pady=(0, 10))
        ttk.Label(outer, textvariable=self.status, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        log_frame = ttk.Frame(outer)
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.log = tk.Text(log_frame, wrap="word", font=("Consolas", 10), state="disabled")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Label(
            outer,
            text="No APK is rebuilt or resigned. Unknown library hashes are never written.",
        ).pack(anchor="w", pady=(10, 0))

        if self.adb_path.get():
            self.root.after(150, self.refresh_devices)

    def append_log(self, message: str, *, clear: bool = False) -> None:
        self.log.configure(state="normal")
        if clear:
            self.log.delete("1.0", "end")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_busy(self, busy: bool, status: str) -> None:
        self.busy = busy
        self.status.set(status)
        for button in self.buttons:
            button.configure(state="disabled" if busy else "normal")

    def browse_adb(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select adb.exe",
            filetypes=[("Android Debug Bridge", "adb.exe"), ("All files", "*.*")],
        )
        if selected:
            self.adb_path.set(selected)
            self.refresh_devices()

    def refresh_devices(self) -> None:
        adb_path = self.adb_path.get()

        def work() -> str:
            client = AdbClient(adb_path)
            devices, problems = client.devices()
            self.root.after(0, lambda: self.set_device_list(devices))
            details = [f"Ready devices: {len(devices)}"]
            details.extend(problems)
            if not devices:
                details.append("Connect USB ADB or run: adb connect PHONE_IP:PORT")
            return "\n".join(details)

        self.run_async("Refreshing devices…", work)

    def set_device_list(self, devices: list[str]) -> None:
        previous = self.device.get()
        self.device_box["values"] = devices
        if previous in devices:
            self.device.set(previous)
        elif devices:
            self.device.set(devices[0])
        else:
            self.device.set("")

    def service(self) -> PatchService:
        serial = self.device.get().strip()
        if not serial:
            raise ToolError("No ready ADB device is selected.")
        return PatchService(self.adb_path.get(), serial)

    def check(self) -> None:
        self.run_service_async("Checking root and installed game…", lambda service: service.check())

    def confirm_apply(self) -> None:
        if messagebox.askyesno(
            "Apply patch?",
            "The game will be force-stopped. The exact original library will be backed up "
            "to this PC and the installed extracted copy will be patched through root.\n\nContinue?",
        ):
            self.run_service_async(
                "Applying and verifying patch…", lambda service: service.apply()
            )

    def confirm_restore(self) -> None:
        if messagebox.askyesno(
            "Restore original?",
            "The game will be force-stopped and the verified PC backup will replace the "
            "supported patched library.\n\nContinue?",
        ):
            self.run_service_async(
                "Restoring and verifying original…", lambda service: service.restore()
            )

    def launch(self) -> None:
        def work(service: PatchService) -> str:
            output = service.adb.launch_game()
            return "Game launch requested.\n" + output

        self.run_service_async("Launching game…", work)

    def open_backups(self) -> None:
        folder = backup_root()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not open {folder}: {exc}")

    def run_async(self, activity: str, operation: Callable[[], str]) -> None:
        if self.busy:
            return
        self.set_busy(True, activity)
        self.append_log(activity, clear=True)

        def worker() -> None:
            try:
                result = operation()
            except Exception as exc:
                self.root.after(0, lambda: self.finish_error(str(exc) or type(exc).__name__))
            else:
                self.root.after(0, lambda: self.finish_success(result))

        threading.Thread(target=worker, daemon=True).start()

    def run_service_async(
        self,
        activity: str,
        operation: Callable[[PatchService], str],
    ) -> None:
        # Capture Tk variables on the UI thread before starting background I/O.
        try:
            service = self.service()
        except Exception as exc:
            self.finish_error(str(exc) or type(exc).__name__)
            return
        self.run_async(activity, lambda: operation(service))

    def finish_success(self, result: str) -> None:
        self.append_log("\n" + result)
        self.set_busy(False, "Ready")

    def finish_error(self, error: str) -> None:
        self.append_log("\nERROR\n" + error)
        self.set_busy(False, "Operation failed")
        messagebox.showerror(APP_TITLE, error)


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
