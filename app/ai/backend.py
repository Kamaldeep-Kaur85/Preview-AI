"""
app/ai/backend.py

Qualcomm Snapdragon & ONNX Runtime Inference Backend Abstraction.
Detects hardware capabilities and selects the genuine execution provider:
- Qualcomm QNN Execution Provider (Snapdragon Hexagon NPU / HTP) when available.
- ONNX Runtime CPU Execution Provider fallback on non-Snapdragon systems.

CRITICAL: Never fakes NPU execution. Only reports what is actually detected.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import logging
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("preview_ai.backend")


# ──────────────────────────────────────────────────────────────────────────────
# Hardware & Provider Detection
# ──────────────────────────────────────────────────────────────────────────────

def detect_device_info() -> Dict[str, Any]:
    """
    Detect physical machine hardware, CPU/NPU processor name, architecture,
    and Qualcomm AI Engine presence.
    """
    machine = platform.machine()
    system = platform.system()
    proc_name = platform.processor() or "Unknown Processor"
    is_arm64 = machine.lower() in ("arm64", "aarch64")

    # On Windows, query registry or environment for exact processor model
    if system == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            if val:
                proc_name = str(val).strip()
            winreg.CloseKey(key)
        except Exception:
            pass

    # Detect Qualcomm Snapdragon chipset signatures
    qualcomm_signatures = [
        "snapdragon", "qualcomm", "kryo", "oryon", "sc8380xp", "sc8280x", "sc7180", "sc7280"
    ]
    is_snapdragon = any(sig in proc_name.lower() for sig in qualcomm_signatures)

    # Check for Qualcomm QNN SDK / libraries
    qnn_sdk_env = os.environ.get("QNN_SDK_ROOT")
    has_qnn_sdk = False
    qnn_libs_found = []

    search_dirs = []
    if qnn_sdk_env:
        search_dirs.append(Path(qnn_sdk_env) / "lib")
    search_dirs.extend([
        Path(r"C:\Qualcomm\QNN"),
        Path(r"C:\Program Files\Qualcomm"),
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32",
    ])

    for base in search_dirs:
        if base.exists():
            for lib_name in ("QnnHtp.dll", "QnnCpu.dll", "QnnSystem.dll", "libQnnHtp.so"):
                matches = list(base.glob(f"**/{lib_name}"))
                if matches:
                    qnn_libs_found.append(matches[0].name)
                    has_qnn_sdk = True

    return {
        "device": proc_name,
        "machine": machine,
        "is_arm64": is_arm64,
        "is_snapdragon": is_snapdragon,
        "has_qnn_sdk": has_qnn_sdk,
        "qnn_libs": list(set(qnn_libs_found)),
        "os": f"{system} {platform.release()}",
    }


def detect_available_providers() -> List[str]:
    """Detect ONNX Runtime providers available in current environment."""
    try:
        import onnxruntime as ort
        return ort.get_available_providers()
    except Exception:
        return []


def is_qnn_available() -> bool:
    """Return True if Qualcomm QNN Execution Provider is genuinely available."""
    providers = detect_available_providers()
    return "QNNExecutionProvider" in providers


# ──────────────────────────────────────────────────────────────────────────────
# Inference Backend Abstraction
# ──────────────────────────────────────────────────────────────────────────────

class InferenceBackend(ABC):
    """Abstract base class for model execution backends."""

    def __init__(self):
        self.session = None
        self.model_path: Optional[Path] = None
        self.load_time_ms: float = 0.0
        self.last_inference_time_ms: float = 0.0
        self.total_inferences: int = 0
        self.backend_name: str = "Abstract"
        self.accelerator_name: str = "Unknown"
        self.provider_name: str = "Unknown"
        self.is_npu: bool = False
        self.mode_description: str = "Offline Local Inference"

    @abstractmethod
    def load(self, model_path: Path) -> bool:
        """Load the ONNX model into session."""
        pass

    @abstractmethod
    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Run on-device inference."""
        pass

    def get_status(self) -> Dict[str, Any]:
        """Return structured runtime status."""
        m_path = Path(self.model_path) if self.model_path else None
        return {
            "backend": self.backend_name,
            "accelerator": self.accelerator_name,
            "provider": self.provider_name,
            "is_npu": self.is_npu,
            "mode": self.mode_description,
            "loaded": self.session is not None,
            "model_path": str(m_path) if m_path else "None",
            "model_name": m_path.name if m_path else "None",
            "load_time_ms": self.load_time_ms,
            "last_inference_time_ms": self.last_inference_time_ms,
            "total_inferences": self.total_inferences,
            "network": "Offline / Local",
        }


class QNNBackend(InferenceBackend):
    """
    Qualcomm QNN Execution Provider backend targeting Snapdragon Hexagon NPU.
    Runs hardware-accelerated tensor operations directly on Snapdragon HTP.
    """

    def __init__(self):
        super().__init__()
        self.backend_name = "QNN"
        self.accelerator_name = "Hexagon NPU"
        self.provider_name = "QNNExecutionProvider"
        self.is_npu = True
        self.mode_description = "On-device (Snapdragon NPU accelerated)"

    def load(self, model_path: Path | str) -> bool:
        try:
            import onnxruntime as ort
            self.model_path = Path(model_path)
            t0 = time.perf_counter()

            # Configure QNN provider options for Hexagon Tensor Processor (HTP)
            qnn_options = {
                "backend_path": "QnnHtp.dll",
                "htp_performance_mode": "burst",
                "htp_graph_finalization_optimization_mode": "3",
            }

            session_options = ort.SessionOptions()
            session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self.session = ort.InferenceSession(
                str(model_path),
                sess_options=session_options,
                providers=["QNNExecutionProvider"],
                provider_options=[qnn_options],
            )
            self.load_time_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(f"QNNBackend loaded {self.model_path.name} on Hexagon NPU in {self.load_time_ms:.2f}ms")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize QNNBackend: {e}")
            self.session = None
            return False

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        if not self.session:
            raise RuntimeError("QNN model session is not loaded")
        t0 = time.perf_counter()
        raw_outputs = self.session.run(None, inputs)
        self.last_inference_time_ms = (time.perf_counter() - t0) * 1000.0
        self.total_inferences += 1

        output_names = [o.name for o in self.session.get_outputs()]
        return {name: raw_outputs[i] for i, name in enumerate(output_names)}


class CPUBackend(InferenceBackend):
    """
    ONNX Runtime CPU Execution Provider fallback backend.
    Enables complete offline operation and testing on Intel/AMD/macOS dev machines.
    Never claims to be NPU execution.
    """

    def __init__(self):
        super().__init__()
        self.backend_name = "ONNX Runtime"
        self.accelerator_name = "CPU"
        self.provider_name = "CPUExecutionProvider"
        self.is_npu = False
        self.mode_description = "Local fallback (CPU Execution Provider)"

    def load(self, model_path: Path | str) -> bool:
        try:
            import onnxruntime as ort
            self.model_path = Path(model_path)
            t0 = time.perf_counter()

            session_options = ort.SessionOptions()
            session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self.session = ort.InferenceSession(
                str(model_path),
                sess_options=session_options,
                providers=["CPUExecutionProvider"],
            )
            self.load_time_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(f"CPUBackend loaded {self.model_path.name} on CPU in {self.load_time_ms:.2f}ms")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize CPUBackend: {e}")
            self.session = None
            return False

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        if not self.session:
            raise RuntimeError("CPU model session is not loaded")
        t0 = time.perf_counter()
        raw_outputs = self.session.run(None, inputs)
        self.last_inference_time_ms = (time.perf_counter() - t0) * 1000.0
        self.total_inferences += 1

        output_names = [o.name for o in self.session.get_outputs()]
        return {name: raw_outputs[i] for i, name in enumerate(output_names)}


# ──────────────────────────────────────────────────────────────────────────────
# Backend Factory & Diagnostics
# ──────────────────────────────────────────────────────────────────────────────

def create_best_backend() -> InferenceBackend:
    """
    Detect available hardware and providers, returning:
    - QNNBackend if Snapdragon + QNNExecutionProvider is available
    - CPUBackend as genuine local fallback otherwise.
    """
    dev_info = detect_device_info()
    providers = detect_available_providers()

    if "QNNExecutionProvider" in providers:
        logger.info("Qualcomm QNNExecutionProvider detected! Using QNNBackend (Hexagon NPU).")
        return QNNBackend()
    else:
        if dev_info["is_snapdragon"]:
            logger.info("Snapdragon hardware detected, but QNNExecutionProvider not active in ORT. Using CPU fallback.")
        else:
            logger.info(f"Device: {dev_info['device']}. Using ONNX Runtime CPU fallback.")
        return CPUBackend()


def get_diagnostic_report(backend: Optional[InferenceBackend] = None) -> Dict[str, Any]:
    """Generate diagnostic details for judging validation."""
    dev_info = detect_device_info()
    providers = detect_available_providers()
    b_status = backend.get_status() if backend else {}

    return {
        "device": dev_info["device"],
        "architecture": dev_info["machine"],
        "os": dev_info["os"],
        "is_snapdragon": dev_info["is_snapdragon"],
        "has_qnn_sdk": dev_info["has_qnn_sdk"],
        "ort_providers": providers,
        "runtime": f"ONNX Runtime v{_get_ort_version()}",
        "backend": b_status.get("backend", "ONNX Runtime" if providers else "Unavailable"),
        "execution_provider": b_status.get("provider", "CPUExecutionProvider" if providers else "None"),
        "accelerator": b_status.get("accelerator", "CPU"),
        "is_npu": b_status.get("is_npu", False),
        "network": "Offline",
        "model_name": b_status.get("model_name", "None"),
        "model_load_ms": b_status.get("load_time_ms", 0.0),
        "inference_ms": b_status.get("last_inference_time_ms", 0.0),
        "total_inferences": b_status.get("total_inferences", 0),
    }


def format_diagnostic_report(backend: Optional[InferenceBackend] = None) -> str:
    """Format diagnostic report into the exact judging format requested."""
    diag = get_diagnostic_report(backend)
    load_ms = f"{diag['model_load_ms']:.2f} ms" if diag["model_load_ms"] > 0 else "Not loaded"
    inf_ms = f"{diag['inference_ms']:.2f} ms" if diag["inference_ms"] > 0 else "0.00 ms (ready)"

    return (
        "Hardware\n"
        "---------\n"
        f"Device: {diag['device']}\n"
        f"Architecture: {diag['architecture']}\n"
        f"Snapdragon Hardware: {'Detected' if diag['is_snapdragon'] else 'Not detected (x86/x64 dev environment)'}\n"
        "\n"
        "AI\n"
        "--\n"
        f"Model: {diag['model_name']}\n"
        f"Runtime: {diag['runtime']}\n"
        f"Execution Provider: {diag['execution_provider']}\n"
        f"Accelerator: {diag['accelerator']}\n"
        f"Network: {diag['network']} (Source code stays on-device)\n"
        "\n"
        "Performance\n"
        "-----------\n"
        f"Model load: {load_ms}\n"
        f"Inference: {inf_ms}\n"
        f"Inference count: {diag['total_inferences']}\n"
    )


def _get_ort_version() -> str:
    try:
        import onnxruntime as ort
        return getattr(ort, "__version__", "unknown")
    except Exception:
        return "not installed"
