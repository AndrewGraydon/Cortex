"""Monkey-patch axengine 0.1.3 to fix NPU session lifecycle bugs.

Call ``patch()`` once at import time (before any InferenceSession is created)
to apply the following fixes:

1. **Idempotent engine init** — ``axclrtEngineInit`` is process-global but
   ``AXCLRTSession.__init__`` calls it every time.  After the first successful
   init we skip re-initialization and instead rebind the saved thread context.

2. **Thread context propagation** — The first ``axclrtSetDevice`` + engine init
   binds an NPU context to the calling thread.  Subsequent sessions created
   from *different* executor threads fail because they have no bound context.
   We save the context from the first session and ``axclrtSetCurrentContext``
   on new threads.

3. **Safe ``__del__``** — During interpreter shutdown CFFI objects can be
   ``None``; guard against ``TypeError`` in ``__del__``.

These patches are idempotent — calling ``patch()`` multiple times is safe.
They target axengine 0.1.3 from the AXERA-TECH local wheel.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_patched = False


def patch() -> None:
    """Apply monkey-patches to axengine._axclrt.AXCLRTSession."""
    global _patched
    if _patched:
        return

    try:
        import axengine._axclrt as _axclrt_mod
        from axengine._axclrt import AXCLRTSession
    except ImportError:
        logger.debug("axengine not installed, skipping compat patches")
        return

    _orig_init = AXCLRTSession.__init__

    # Module-level state shared across all sessions
    _saved_context = [None]  # Mutable container to allow closure mutation

    def _patched_init(self, path_or_bytes, sess_options=None, provider_options=None, **kwargs):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN003
        """Patched __init__ that handles engine re-init and thread context."""
        from axengine._axclrt import axclrt_cffi, axclrt_lib
        from axengine._axclrt_types import VNPUType
        from axengine._base_session import Session

        Session.__init__(self)

        self._device_index = 0
        self._io = None
        self._model_id = None

        if provider_options is not None and "device_id" in provider_options[0]:
            self._device_index = provider_options[0].get("device_id", 0)

        # Get device list
        lst = axclrt_cffi.new("axclrtDeviceList *")
        ret = axclrt_lib.axclrtGetDeviceList(lst)
        if ret != 0 or lst.num == 0:
            msg = f"Get AXCL device failed 0x{ret:08x}, find total {lst.num} device."
            raise RuntimeError(msg)
        if self._device_index >= lst.num:
            msg = f"Device index {self._device_index} out of range ({lst.num} devices)."
            raise RuntimeError(msg)

        self._device_id = lst.devices[self._device_index]
        ret = axclrt_lib.axclrtSetDevice(self._device_id)
        if ret != 0:
            msg = f"Set AXCL device failed 0x{ret:08x}."
            raise RuntimeError(msg)

        # --- FIX 1: Idempotent engine initialization ---
        if not _axclrt_mod._is_axclrt_engine_initialized:
            vnpu_type = axclrt_cffi.cast("axclrtEngineVNpuKind", VNPUType.DISABLED.value)
            ret = axclrt_lib.axclrtEngineInit(vnpu_type)
            if ret != 0:
                vnpu = axclrt_cffi.new("axclrtEngineVNpuKind *")
                ret2 = axclrt_lib.axclrtEngineGetVNpuKind(vnpu)
                if ret2 != 0:
                    msg = f"axclrtEngineInit failed 0x{ret:08x} and no existing engine."
                    raise RuntimeError(msg)
                logger.warning(
                    "NPU engine already initialized as vnpu=%s (expected first init)",
                    vnpu[0],
                )
            _axclrt_mod._is_axclrt_engine_initialized = True
        else:
            # --- FIX 2: Rebind saved context to current thread ---
            if _saved_context[0] is not None:
                ret = axclrt_lib.axclrtSetCurrentContext(_saved_context[0][0])
                if ret != 0:
                    logger.warning("axclrtSetCurrentContext returned 0x%08x", ret)

        # Get SOC name
        self.soc_name = axclrt_cffi.string(axclrt_lib.axclrtGetSocName()).decode()

        # Get or create thread context
        self._thread_context = axclrt_cffi.new("axclrtContext *")
        ret = axclrt_lib.axclrtGetCurrentContext(self._thread_context)
        if ret != 0:
            # Last resort: try setting saved context then retrying
            if _saved_context[0] is not None:
                axclrt_lib.axclrtSetCurrentContext(_saved_context[0][0])
                ret = axclrt_lib.axclrtGetCurrentContext(self._thread_context)
            if ret != 0:
                msg = "axclrtGetCurrentContext failed (no NPU context for thread)"
                raise RuntimeError(msg)

        # Save context for future threads
        if _saved_context[0] is None:
            _saved_context[0] = self._thread_context

        # Model handle + context
        self._model_id = axclrt_cffi.new("uint64_t *")
        self._context_id = axclrt_cffi.new("uint64_t *")

        # Get VNPU type
        from axengine._axclrt import _get_vnpu_type

        self._vnpu_type = _get_vnpu_type()

        # Load model
        ret = self._load(path_or_bytes)
        if ret != 0:
            msg = "Failed to load model."
            raise RuntimeError(msg)

        # Get model info
        self._info = self._get_info()
        self._shape_count = self._get_shape_count()
        self._inputs = self._get_inputs()
        self._outputs = self._get_outputs()

        # Prepare IO
        self._io = self._prepare_io()

        _axclrt_mod._all_model_instances.append(self)

    # --- FIX 3: Safe __del__ ---
    # Cannot use contextlib.suppress here — modules may be None during shutdown
    def _patched_del(self) -> None:  # type: ignore[no-untyped-def]  # noqa: ANN001
        if self._model_id is None:
            return
        try:  # noqa: SIM105
            self._unload()
        except Exception:
            pass
        try:  # noqa: SIM105
            _axclrt_mod._all_model_instances.remove(self)
        except (ValueError, TypeError):
            pass

    AXCLRTSession.__init__ = _patched_init
    AXCLRTSession.__del__ = _patched_del

    _patched = True
    logger.info("axengine 0.1.3 compat patches applied")
