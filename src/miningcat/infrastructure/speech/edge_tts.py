import asyncio

# edge-tts offsets and durations are in 100-nanosecond ticks.
TICKS_PER_SECOND = 10_000_000


class EdgeTts:
    """Microsoft Edge's online text-to-speech voices (edge-tts)."""

    @staticmethod
    async def stream(text: str, voice: str) -> tuple[bytes, list[dict]]:
        """The MP3 of the text read by the voice, and its sentence boundary events."""
        import edge_tts

        audio = bytearray()
        sentences: list[dict] = []
        async for chunk in edge_tts.Communicate(text, voice).stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                sentences.append(chunk)
        return bytes(audio), sentences

    def synthesize(self, text: str, voice: str) -> bytes:
        """The MP3 of the text read by the voice."""
        audio, _ = asyncio.run(self.stream(text, voice))
        return audio
