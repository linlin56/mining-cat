"""The sound of the captured window's app, recorded with ScreenCaptureKit (macOS 13 or later), with the same Screen
Recording permission as the window capture."""
import queue

import numpy as np

from miningcat.infrastructure.capture.audio import AudioRecorder
from miningcat.infrastructure.capture.base import CaptureError

RATE = 48000
_TIMEOUT_S = 5

_sink_class = None


# Defined once, when the first recorder starts: pyobjc classes are registered with the Objective-C runtime by name.
def _audio_sink_class():
    global _sink_class
    if _sink_class is None:
        import objc
        import CoreMedia
        import ScreenCaptureKit
        from Foundation import NSObject

        class MiningCatAudioSink(NSObject, protocols=[objc.protocolNamed("SCStreamOutput")]):
            """Receives the stream's sound on its dispatch queue, as mono float32 chunks, into a ring."""

            def initWithRing_(self, ring):
                self = objc.super(MiningCatAudioSink, self).init()
                if self is not None:
                    self.ring = ring
                return self

            def stream_didOutputSampleBuffer_ofType_(self, _stream, sample_buffer, output_type):
                if output_type != ScreenCaptureKit.SCStreamOutputTypeAudio:
                    return
                block = CoreMedia.CMSampleBufferGetDataBuffer(sample_buffer)
                if block is None:
                    return
                length = CoreMedia.CMBlockBufferGetDataLength(block)
                status, data = CoreMedia.CMBlockBufferCopyDataBytes(block, 0, length, None)
                if status == 0:
                    self.ring.write(np.frombuffer(bytes(data), dtype=np.float32))

        _sink_class = MiningCatAudioSink
    return _sink_class


class MacOSAudioRecorder(AudioRecorder):
    """`application`: the SCRunningApplication of the captured window. Only its sound is recorded: not MiningCat's,
    nor the music or the notifications of other apps."""

    def __init__(self, SCK, display, application):
        super().__init__(RATE)
        import CoreMedia
        import dispatch

        self._SCK = SCK
        content_filter = SCK.SCContentFilter.alloc().initWithDisplay_includingApplications_exceptingWindows_(
            display, [application], [])
        config = SCK.SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        # "The current process" is the app MiningCat was launched from (Terminal, VS Code...): a game launched from the
        # same terminal would be silent.
        config.setExcludesCurrentProcessAudio_(False)
        config.setSampleRate_(RATE)
        config.setChannelCount_(1)
        # The stream's own images aren't used (the window capture takes its own): as small and rare as can be.
        config.setWidth_(2)
        config.setHeight_(2)
        config.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 1))
        self._sink = _audio_sink_class().alloc().initWithRing_(self.ring)
        self._stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(content_filter, config, None)
        self._queue = dispatch.dispatch_queue_create(b"miningcat.capture.audio", None)
        added, error = self._stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self._sink, SCK.SCStreamOutputTypeAudio, self._queue, None)
        if not added:
            raise CaptureError(f"Couldn't record the window's sound: {error.localizedDescription() if error else 'unknown error'}")
        self._started = False

    def start(self) -> None:
        self._started = self._call(self._stream.startCaptureWithCompletionHandler_, "start recording the sound")

    def close(self) -> None:
        if self._started:
            self._started = False
            try:
                self._call(self._stream.stopCaptureWithCompletionHandler_, "stop recording the sound")
            except CaptureError:
                pass

    @staticmethod
    def _call(method, action: str) -> bool:
        results = queue.Queue()
        method(results.put)
        try:
            error = results.get(timeout=_TIMEOUT_S)
        except queue.Empty:
            raise CaptureError(f"macOS didn't {action} in time (timeout)") from None
        if error is not None:
            raise CaptureError(f"Couldn't {action}: {error.localizedDescription()}")
        return True
