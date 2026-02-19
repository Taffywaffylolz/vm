# Windows 10 VM Builder (RTX 4080 / i9-14700K profile)

This app provides a local web UI to configure and run a **Windows 10** virtual machine with the requested target profile:

- GPU target: **RTX 4080** (via VFIO passthrough)
- CPU target: **i9-14700K-like profile** (20 cores, 2 threads)
- Memory: **16 GB**
- Storage: **1 TB qcow2 SSD image**

> Note: Exact consumer GPU emulation is not possible in software. To get a *real* RTX 4080 inside the guest, enable VFIO passthrough and set the correct PCI IDs.

## 1) Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install host tools (Ubuntu/Debian example):

```bash
sudo apt-get install -y qemu-kvm qemu-utils ovmf
```

## 2) Run app

```bash
python app.py
```

Open http://localhost:8000

## 3) Use the UI

1. Set `Windows 10 ISO path`
2. (Optional) Set `VirtIO ISO path`
3. Save config
4. Click **Create 1TB qcow2 disk**
5. Click **Start VM**

## RTX 4080 passthrough checklist

- Enable IOMMU in BIOS + kernel (`intel_iommu=on iommu=pt`)
- Bind RTX 4080 + HDMI audio functions to `vfio-pci`
- Set GPU PCI IDs in the app and enable passthrough

## Limitations

- No legal Windows ISO/license is bundled.
- Host must support virtualization and provide the physical GPU for passthrough.
