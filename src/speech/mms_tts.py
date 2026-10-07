"""Text-to-speech with Meta's MMS voices (VITS models of the Massively Multilingual Speech project, CC BY-NC 4.0:
non-commercial use only), for the languages Edge has no voice for. The Taigi voice was trained on Bible
recordings written in Pe̍h-ōe-jī: the text is read in POJ, whatever it's written in."""

import numpy as np

from speech import SpeechError, encode_mp3, require

# voice id -> (Hugging Face model, language). Ids look like Edge's (locale first), so that the voice lists can
# tell their language.
VOICES = {
    "nan-TW-MmsTaigi": ("facebook/mms-tts-nan", "nan"),
}
VOICE_LABELS = {
    "nan-TW-MmsTaigi": "MMS - Taigi (local, Meta MMS-TTS)",
}
PAUSE_SECONDS = 0.3   # silence between two sentences of a chapter
SEED = 0              # VITS draws its durations at random: the same text always sounds the same

_models: dict[str, tuple] = {}


def is_local(voice: str) -> bool:
    return voice in VOICES


def _model(voice: str):
    if voice not in _models:
        transformers = require("transformers", "The MMS voices")
        repo = VOICES[voice][0]
        print(f"Loading the MMS voice ({repo})...")
        _models[voice] = (transformers.VitsModel.from_pretrained(repo).eval(), transformers.AutoTokenizer.from_pretrained(repo))
    return _models[voice]


def _text_for(voice: str, text: str) -> str:
    if VOICES[voice][1] == "nan":
        from mining.taigi import tts_text
        return tts_text(text)
    return text


def synthesize(text: str, voice: str) -> tuple[np.ndarray, int]:
    """(mono float32 samples, sample rate) of the text read by the voice."""
    if not is_local(voice):
        raise SpeechError(f"Unknown local voice: {voice!r}")
    torch = require("torch", "The MMS voices")
    model, tokenizer = _model(voice)
    rate = model.config.sampling_rate
    inputs = tokenizer(_text_for(voice, text), return_tensors="pt")
    if inputs["input_ids"].shape[-1] <= 1:  # nothing it can read (punctuation, numbers)
        return np.zeros(0, dtype=np.float32), rate
    torch.manual_seed(SEED)
    with torch.inference_mode():
        waveform = model(**inputs).waveform[0].numpy()
    return waveform.astype(np.float32), rate


def synthesize_mp3(text: str, voice: str) -> bytes:
    samples, rate = synthesize(text, voice)
    if not len(samples):
        raise SpeechError("There's nothing the voice can read in this text.")
    return encode_mp3(samples, rate)


def synthesize_chapter(sentences: list[str], voice: str, audio_path) -> list[tuple[float, float, str]]:
    """Reads the sentences one after the other into an MP3 file. Returns the (start, end, sentence) of each."""
    pieces, timed, position, rate = [], [], 0.0, 16000
    for sentence in sentences:
        samples, rate = synthesize(sentence, voice)
        if not len(samples):
            if timed:  # punctuation, numbers: shown with the sentence before
                timed[-1] = (*timed[-1][:2], timed[-1][2] + sentence)
            continue
        duration = len(samples) / rate
        timed.append((position, position + duration, sentence))
        pieces += [samples, np.zeros(int(PAUSE_SECONDS * rate), dtype=np.float32)]
        position += duration + PAUSE_SECONDS
    if not pieces:
        raise SpeechError("There's nothing the voice can read in this text.")
    encode_mp3(np.concatenate(pieces), rate, audio_path)
    return timed
