"""OmniVoice, in its own process and its own environment (.venv-omnivoice: it needs transformers 5, Qwen3-ASR pins
4.57.6): `python -m miningcat.infrastructure.speech.omnivoice_worker` reads one JSON request per line on stdin and
answers each one with a line of JSON (see omnivoice_tts.py). It only imports the standard library, numpy, torch and
omnivoice: the rest of MiningCat isn't installed in its environment.

A request: {"text", "language", "num_step", "voice", "reference_text", "seed", "output"}. `voice` is the file of the
language's voice: when it doesn't exist yet, the model makes up a voice reading `reference_text`, and saves it there
(OmniVoice's voice clone prompt), so that every sentence of the language is then read by the same voice. The samples
(mono float32) are written to `output`. The answer: {"sample_rate"}, or {"error"}."""
import json
import os
import sys

RESULT_PREFIX = "@@miningcat-omnivoice "
MODEL = "k2-fsa/OmniVoice"
# The voice of a language is made once: the best quality, whatever the steps chosen for the sentences.
VOICE_STEPS = 32


def _answer(value: dict) -> None:
    print(RESULT_PREFIX + json.dumps(value, ensure_ascii=False), flush=True)


def _device(torch) -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Voices:
    """The voice clone prompts of the languages, loaded once."""

    def __init__(self, model, torch, voice_clone_prompt):
        self._model, self._torch, self._prompt_class = model, torch, voice_clone_prompt
        self._prompts = {}

    def get(self, request: dict):
        path = request["voice"]
        if path not in self._prompts:
            self._prompts[path] = self._load(path) if os.path.exists(path) else self._make(request)
        return self._prompts[path]

    def _load(self, path: str):
        return self._prompt_class.load(path)

    def _make(self, request: dict):
        torch, model = self._torch, self._model
        torch.manual_seed(int(request.get("seed") or 0))
        audio = model.generate(text=request["reference_text"], language=request["language"], num_step=VOICE_STEPS)[0]
        prompt = model.create_voice_clone_prompt(
            (torch.from_numpy(audio.astype("float32")), model.sampling_rate), ref_text=request["reference_text"],
        )
        os.makedirs(os.path.dirname(request["voice"]) or ".", exist_ok=True)
        prompt.save(request["voice"])
        return prompt


def main() -> None:
    try:
        import numpy as np
        import torch
        from omnivoice import OmniVoice, VoiceClonePrompt

        device = _device(torch)
        dtype = torch.float16 if device == "cuda" else torch.float32
        model = OmniVoice.from_pretrained(MODEL, device_map=device, dtype=dtype)
    except Exception as exc:
        _answer({"error": f"{type(exc).__name__}: {exc}"})
        return
    voices = Voices(model, torch, VoiceClonePrompt)
    _answer({"ready": True, "device": device})

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            prompt = voices.get(request)
            torch.manual_seed(int(request.get("seed") or 0))  # the same sentence always sounds the same
            audio = model.generate(
                text=request["text"], language=request["language"], voice_clone_prompt=prompt,
                num_step=int(request["num_step"]),
            )[0]
            np.asarray(audio, dtype=np.float32).tofile(request["output"])
            answer = {"sample_rate": model.sampling_rate}
        except Exception as exc:
            answer = {"error": f"{type(exc).__name__}: {exc}"}
        _answer(answer)


if __name__ == "__main__":
    main()
