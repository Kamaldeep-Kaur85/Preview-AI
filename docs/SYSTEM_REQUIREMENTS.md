# PreView AI — System Requirements

This document outlines the verified minimum and recommended system requirements for running PreView AI.

---

## Hardware Requirements

| Component | Minimum (Verified) | Recommended |
|:---|:---|:---|
| **Operating System** | Windows 10 (Build 19041+) or Windows 11 | Windows 11 (23H2 or newer) |
| **Architecture** | x86-64 (Intel / AMD 64-bit) | x86-64 or ARM64 (Qualcomm Snapdragon X Elite / Plus) |
| **Processor (CPU)** | Intel Core i5 / AMD Ryzen 5 or equivalent | Intel Core i7 / AMD Ryzen 7 / Snapdragon X Elite |
| **RAM (Memory)** | 4 GB RAM | 8 GB RAM or higher |
| **Disk Space** | 450 MB free space (executable + model + temp) | 1 GB free space (for caching large multi-thousand file repos) |
| **Display Resolution** | 1280 × 720 (minimum GUI size 540 × 400) | 1920 × 1080 or higher |

---

## AI Hardware Acceleration

| Acceleration Path | Hardware Target | Status | Measured Latency |
|:---|:---|:---|:---|
| **CPU Execution Provider** | Any standard x86-64 / ARM64 CPU | **VERIFIED** | 1.61 ms P50 (Intel i7-10610U) |
| **Qualcomm QNN HTP Provider** | Qualcomm Snapdragon Hexagon NPU | **VERIFIED** | 0.34 ms P50 (Snapdragon X Elite) |
| **GPU (DirectML / CUDA)** | Dedicated or integrated GPU | *Not yet verified / Planned* | Fallback to CPU |

---

## Software & Runtime Requirements

### For End Users (`PreView-AI.exe` Standalone)
- **Python**: **NOT REQUIRED** (Python 3.13 runtime is fully self-contained in the standalone executable).
- **Microsoft Visual C++ Redistributable**: 2015–2022 x64 runtime (standard on modern Windows 10/11 updates).
- **Internet Connection**: **NOT REQUIRED** (PreView AI operates 100% locally and offline; no telemetry or cloud APIs are required).

### For Developers (Running From Source)
- **Python**: Version 3.10 through 3.13 (Python 3.13 verified).
- **Package Manager**: `pip` with `setuptools` and `wheel`.
- **Git**: Required for repository cloning and version management.
