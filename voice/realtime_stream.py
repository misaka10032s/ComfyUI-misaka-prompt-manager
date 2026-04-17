"""
Real-time voice conversion stream.

Runs in a separate process (multiprocessing) so audio I/O does not block
ComfyUI's main thread. Uses a ring-buffer with extra context on both sides
to reduce boundary artifacts.

Architecture:
    Main process (ComfyUI)
      └─ spawn RealtimeVCStream process
              sounddevice callback → ring buffer → RVCConverter → output
"""

import multiprocessing
import threading
import numpy as np
from pathlib import Path


class RealtimeVCStream:
    def __init__(
        self,
        converter,                       # RVCConverter instance (in main process)
        input_device=None,
        output_device=None,
        block_time_ms: int = 250,
        extra_context_ms: int = 2500,
        crossfade_ms: int = 50,
        f0_method: str = "rmvpe",
    ):
        self.converter = converter
        self.input_device = input_device
        self.output_device = output_device
        self.block_time_ms = block_time_ms
        self.extra_context_ms = extra_context_ms
        self.crossfade_ms = crossfade_ms
        self.f0_method = f0_method

        self._process: multiprocessing.Process | None = None
        self._stop_event = multiprocessing.Event()
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._process is not None and self._process.is_alive():
                print("[MisakaVC] Stream already running.")
                return

            self._stop_event.clear()
            self._process = multiprocessing.Process(
                target=_stream_worker,
                args=(
                    str(Path(__file__).parent),   # voice package dir for imports
                    self.converter.model_path,
                    self.converter.index_path,
                    self.converter.device,
                    self.input_device,
                    self.output_device,
                    self.block_time_ms,
                    self.extra_context_ms,
                    self.crossfade_ms,
                    self.f0_method,
                    self._stop_event,
                ),
                daemon=True,
            )
            self._process.start()
            print(f"[MisakaVC] Realtime stream started (PID {self._process.pid})")

    def stop(self):
        with self._lock:
            if self._process is None:
                return
            self._stop_event.set()
            self._process.join(timeout=5.0)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=2.0)
            self._process = None
            print("[MisakaVC] Realtime stream stopped.")

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.is_alive()

    @staticmethod
    def list_devices() -> list:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            return [
                {
                    "index": i,
                    "name": d["name"],
                    "max_input_channels": d["max_input_channels"],
                    "max_output_channels": d["max_output_channels"],
                }
                for i, d in enumerate(devices)
            ]
        except ImportError:
            print("[MisakaVC] sounddevice not available. "
                  "Install with: pip install sounddevice")
            return []


# ---------------------------------------------------------------------------
# Worker (runs in a separate process — must use absolute imports)
# ---------------------------------------------------------------------------

def _stream_worker(
    voice_dir: str,
    model_path: str,
    index_path: str,
    device: str,
    input_device,
    output_device,
    block_time_ms: int,
    extra_context_ms: int,
    crossfade_ms: int,
    f0_method: str,
    stop_event: multiprocessing.Event,
):
    import sys
    # Ensure the custom node package is importable
    node_root = str(Path(voice_dir).parent)
    if node_root not in sys.path:
        sys.path.insert(0, node_root)

    try:
        import sounddevice as sd
        import numpy as np
        from voice.rvc_wrapper import RVCConverter
        from voice.resampler import resample

        converter = RVCConverter(model_path, index_path, device)

        sr = converter._tgt_sr or 40000
        block_samples = int(block_time_ms * sr / 1000)
        ctx_samples = int(extra_context_ms * sr / 1000)
        fade_samples = int(crossfade_ms * sr / 1000)

        # Ring buffer: [ctx | block | ctx]
        buf_len = ctx_samples + block_samples + ctx_samples
        ring = np.zeros(buf_len, dtype=np.float32)
        prev_tail = np.zeros(fade_samples, dtype=np.float32)

        def callback(indata, outdata, frames, time_info, status):
            nonlocal ring, prev_tail

            if stop_event.is_set():
                outdata[:] = 0
                return

            chunk = indata[:, 0].astype(np.float32)

            # Shift ring buffer left and append new chunk
            ring = np.roll(ring, -frames)
            ring[-frames:] = chunk[:frames] if len(chunk) >= frames else np.pad(chunk, (0, frames - len(chunk)))

            try:
                converted, out_sr = converter.convert(
                    ring.copy(), sr, f0_method=f0_method
                )
                if out_sr != sr:
                    converted = resample(converted, out_sr, sr)

                # Extract only the center block
                output_block = converted[ctx_samples: ctx_samples + block_samples]

                # Cross-fade with tail of previous output to remove clicks
                f = min(fade_samples, len(output_block), len(prev_tail))
                if f > 0:
                    t = np.linspace(0.0, 1.0, f, dtype=np.float32)
                    output_block[:f] = prev_tail[-f:] * (1.0 - t) + output_block[:f] * t

                prev_tail = output_block[-fade_samples:].copy() if fade_samples > 0 else np.array([], dtype=np.float32)

                n = min(frames, len(output_block))
                outdata[:n, 0] = output_block[:n]
                if n < frames:
                    outdata[n:] = 0

            except Exception as e:
                print(f"[MisakaVC] Callback error: {e}")
                outdata[:] = 0

        with sd.Stream(
            samplerate=sr,
            blocksize=block_samples,
            dtype="float32",
            channels=1,
            callback=callback,
            device=(input_device, output_device),
        ):
            while not stop_event.is_set():
                sd.sleep(100)

    except ImportError as e:
        print(f"[MisakaVC] Stream worker missing dependency: {e}")
    except Exception as e:
        print(f"[MisakaVC] Stream worker error: {e}")
