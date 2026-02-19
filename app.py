from __future__ import annotations

import html
import json
import os
import shlex
import signal
import subprocess
import urllib.parse
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import List

APP_ROOT = Path(__file__).resolve().parent
STATE_FILE = APP_ROOT / "vm_state.json"
PID_FILE = APP_ROOT / "vm.pid"


@dataclass
class VmSpec:
    name: str = "win10-rtx4080"
    memory: str = "16G"
    disk_size: str = "1T"
    vcpus: int = 20
    threads: int = 2
    machine: str = "q35"


@dataclass
class VmConfig:
    windows_iso: str = ""
    virtio_iso: str = ""
    disk_path: str = "./win10-rtx4080.qcow2"
    enable_kvm: bool = True
    ovmf_code: str = "/usr/share/OVMF/OVMF_CODE.fd"
    ovmf_vars: str = "./OVMF_VARS.fd"
    gpu_passthrough: bool = False
    gpu_pci_id: str = "01:00.0"
    gpu_audio_pci_id: str = "01:00.1"


def load_config() -> VmConfig:
    if not STATE_FILE.exists():
        return VmConfig()
    return VmConfig(**json.loads(STATE_FILE.read_text(encoding="utf-8")))


def save_config(config: VmConfig) -> None:
    STATE_FILE.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")


def vm_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        os.kill(int(PID_FILE.read_text().strip()), 0)
        return True
    except Exception:
        return False


def build_qemu_command(spec: VmSpec, cfg: VmConfig) -> List[str]:
    accel = "kvm" if cfg.enable_kvm else "tcg"
    cpu = "host" if cfg.enable_kvm else "max"
    cmd = [
        "qemu-system-x86_64",
        "-name",
        spec.name,
        "-machine",
        f"{spec.machine},accel={accel}",
        "-cpu",
        cpu,
        "-smp",
        f"cores={spec.vcpus},threads={spec.threads},sockets=1",
        "-m",
        spec.memory,
        "-drive",
        f"if=pflash,format=raw,readonly=on,file={cfg.ovmf_code}",
        "-drive",
        f"if=pflash,format=raw,file={cfg.ovmf_vars}",
        "-drive",
        f"file={cfg.disk_path},if=virtio,format=qcow2,cache=writeback",
        "-netdev",
        "user,id=net0",
        "-device",
        "virtio-net-pci,netdev=net0",
        "-usb",
        "-device",
        "usb-tablet",
    ]
    if cfg.windows_iso:
        cmd.extend(["-drive", f"file={cfg.windows_iso},media=cdrom"])
    if cfg.virtio_iso:
        cmd.extend(["-drive", f"file={cfg.virtio_iso},media=cdrom"])
    if cfg.gpu_passthrough:
        cmd.extend(["-device", f"vfio-pci,host={cfg.gpu_pci_id},multifunction=on"])
        if cfg.gpu_audio_pci_id:
            cmd.extend(["-device", f"vfio-pci,host={cfg.gpu_audio_pci_id}"])
    else:
        cmd.extend(["-device", "virtio-vga"])
    return cmd


def style() -> str:
    return (APP_ROOT / "static/style.css").read_text(encoding="utf-8")


def render_page(message: str = "") -> bytes:
    spec = VmSpec()
    cfg = load_config()
    cmd = " ".join(shlex.quote(c) for c in build_qemu_command(spec, cfg))

    def esc(v: str) -> str:
        return html.escape(v, quote=True)

    checked = lambda b: "checked" if b else ""
    status = '<span class="ok">Running</span>' if vm_running() else '<span class="error">Stopped</span>'
    msg_block = f"<li class='ok'>{esc(message)}</li>" if message else ""
    page = f"""<!doctype html><html><head><meta charset='utf-8'><title>VM Builder</title><style>{style()}</style></head>
<body><main class='container'><h1>Windows 10 VM Builder</h1>
<p class='subhead'>Target profile: <strong>RTX 4080</strong> + <strong>i9-14700K</strong> + <strong>16GB RAM</strong> + <strong>1TB SSD</strong></p>
<ul class='alerts'>{msg_block}</ul>
<h2>Fixed hardware</h2><ul><li>vCPU cores: {spec.vcpus} (threads: {spec.threads})</li><li>Memory: {spec.memory}</li><li>Disk capacity: {spec.disk_size}</li></ul>
<h2>VM Configuration</h2>
<form method='post' action='/save' class='grid'>
<label>Windows 10 ISO path<input name='windows_iso' value='{esc(cfg.windows_iso)}'></label>
<label>VirtIO ISO path<input name='virtio_iso' value='{esc(cfg.virtio_iso)}'></label>
<label>Disk file path<input name='disk_path' value='{esc(cfg.disk_path)}'></label>
<label>OVMF CODE<input name='ovmf_code' value='{esc(cfg.ovmf_code)}'></label>
<label>OVMF VARS<input name='ovmf_vars' value='{esc(cfg.ovmf_vars)}'></label>
<label class='checkbox'><input type='checkbox' name='enable_kvm' {checked(cfg.enable_kvm)}> Enable KVM acceleration</label>
<label class='checkbox'><input type='checkbox' name='gpu_passthrough' {checked(cfg.gpu_passthrough)}> Enable RTX 4080 passthrough via VFIO</label>
<label>GPU PCI ID<input name='gpu_pci_id' value='{esc(cfg.gpu_pci_id)}'></label>
<label>GPU Audio PCI ID<input name='gpu_audio_pci_id' value='{esc(cfg.gpu_audio_pci_id)}'></label>
<button type='submit'>Save config</button></form>
<h2>Runtime</h2><p>Status: {status}</p>
<div class='actions'>
<form method='post' action='/create-disk'><button>Create 1TB qcow2 disk</button></form>
<form method='post' action='/start'><button>Start VM</button></form>
<form method='post' action='/stop'><button>Stop VM</button></form></div>
<h2>Generated launch command</h2><pre>{esc(cmd)}</pre></main></body></html>"""
    return page.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        body = render_page()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        msg = "Done"
        if self.path == "/save":
            cfg = VmConfig(
                windows_iso=data.get("windows_iso", [""])[0].strip(),
                virtio_iso=data.get("virtio_iso", [""])[0].strip(),
                disk_path=data.get("disk_path", ["./win10-rtx4080.qcow2"])[0].strip(),
                enable_kvm="enable_kvm" in data,
                ovmf_code=data.get("ovmf_code", ["/usr/share/OVMF/OVMF_CODE.fd"])[0].strip(),
                ovmf_vars=data.get("ovmf_vars", ["./OVMF_VARS.fd"])[0].strip(),
                gpu_passthrough="gpu_passthrough" in data,
                gpu_pci_id=data.get("gpu_pci_id", ["01:00.0"])[0].strip(),
                gpu_audio_pci_id=data.get("gpu_audio_pci_id", ["01:00.1"])[0].strip(),
            )
            save_config(cfg)
            msg = "Configuration saved"
        elif self.path == "/create-disk":
            cfg = load_config()
            spec = VmSpec()
            result = subprocess.run(["qemu-img", "create", "-f", "qcow2", cfg.disk_path, spec.disk_size], capture_output=True, text=True)
            msg = "Disk created" if result.returncode == 0 else f"Disk creation failed: {result.stderr.strip()}"
        elif self.path == "/start":
            if vm_running():
                msg = "VM already running"
            else:
                proc = subprocess.Popen(build_qemu_command(VmSpec(), load_config()), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                PID_FILE.write_text(str(proc.pid), encoding="utf-8")
                msg = f"VM started (PID {proc.pid})"
        elif self.path == "/stop":
            if PID_FILE.exists():
                pid = int(PID_FILE.read_text().strip())
                try:
                    os.kill(pid, signal.SIGTERM)
                    msg = f"Stopped PID {pid}"
                except ProcessLookupError:
                    msg = "Process already stopped"
                PID_FILE.unlink(missing_ok=True)
            else:
                msg = "No VM pid file"
        body = render_page(msg)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
