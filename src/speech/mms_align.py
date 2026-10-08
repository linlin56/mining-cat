"""Forced alignment of a book's text on its audiobook with Meta's MMS aligner (torchaudio's MMS_FA: a CTC model of
romanized letters trained on 1,100+ languages), for the languages Whisper can't align. The text is romanized
(Taigi: Hanji read as Tâi-lô, without tones), then aligned sentence by sentence.

A chapter is too long to align at once (the cost grows with audio length × text length): it's aligned a few
sentences at a time, in a window of audio a bit longer than they should take to read. The last sentence of a window
may be stretched over the speech that follows it, so it's aligned again at the start of the next window."""

import re
import unicodedata

import numpy as np
from tqdm import tqdm

from speech import SAMPLE_RATE, SpeechError, load_audio, require

FRAME_SECONDS = 0.02            # one emission per 320 samples
WINDOW_FRAMES = 1500            # the model hears 30 s at a time...
CONTEXT_FRAMES = 50             # ...with 1 s of context on each side
GROUP_LETTERS = 600             # letters aligned together (about 40 s of speech)
WINDOW_MARGIN = 1.5             # audio window: the group's expected duration × this...
WINDOW_EXTRA_FRAMES = 750       # ...+ 15 s


def _romanizer(language: str):
    if language == "nan":
        from mining.taigi import alignment_letters
        return alignment_letters

    def letters(text: str) -> str:  # a Latin-script language: its letters without accents
        plain = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
        return " ".join(re.findall(r"[a-z']+", plain.lower()))
    return letters


class Aligner:
    def __init__(self):
        torchaudio = require("torchaudio", "Aligning a book with the MMS aligner")
        self.torch = require("torch", "Aligning a book with the MMS aligner")
        bundle = torchaudio.pipelines.MMS_FA
        print("Loading the MMS aligner...")
        self.device = "cuda" if self.torch.cuda.is_available() else "cpu"
        self.model = bundle.get_model(with_star=False).to(self.device).eval()
        self.dictionary = bundle.get_dict(star=None)

    def emissions(self, samples: np.ndarray) -> np.ndarray:
        """Log-probabilities of the letters, one row per 20 ms of audio."""
        torch = self.torch
        hop = int(SAMPLE_RATE * FRAME_SECONDS)
        window, context = WINDOW_FRAMES * hop, CONTEXT_FRAMES * hop
        rows = []
        with torch.inference_mode():
            for start in range(0, len(samples), window):
                left = min(context, start)
                piece = samples[start - left:start + window + context]
                if len(piece) - left < 400:  # less than one frame left
                    break
                emission, _ = self.model(torch.from_numpy(piece).unsqueeze(0).to(self.device))
                emission = torch.log_softmax(emission[0], dim=-1).cpu().numpy()
                wanted = min(WINDOW_FRAMES, (len(samples) - start) // hop)
                emission = emission[left // hop:left // hop + wanted]
                if len(emission) < wanted:  # the frame count rounds down: keep the timeline exact
                    emission = np.concatenate([emission, np.repeat(emission[-1:], wanted - len(emission), axis=0)])
                rows.append(emission)
        return np.concatenate(rows) if rows else np.zeros((0, len(self.dictionary)), dtype=np.float32)

    def tokens(self, letters: str) -> list[int]:
        return [self.dictionary[c] for c in letters if c in self.dictionary and c != "-"]

    def align(self, audio_file, sentences: list[str], language: str, progress: bool = True) -> list[tuple[float, float, str]]:
        """(start, end, sentence) of each sentence of the text read in the audio file."""
        romanize = _romanizer(language)
        units: list[tuple[str, list[int]]] = []
        pending = ""
        for sentence in sentences:
            tokens = self.tokens(romanize(sentence))
            if tokens:
                units.append((pending + sentence, tokens))
                pending = ""
            elif units:  # nothing to pronounce (punctuation, numbers): goes with the sentence before
                units[-1] = (units[-1][0] + sentence, units[-1][1])
            else:
                pending += sentence
        if not units:
            return []
        emission = self.emissions(load_audio(audio_file))
        return align_emission(emission, units, progress=progress)


def align_emission(emission: np.ndarray, units: list[tuple[str, list[int]]], progress: bool = False) -> list[tuple[float, float, str]]:
    """(start, end, text) of each (text, tokens) unit, aligned in order on the emission, a few units at a time."""
    total_frames = len(emission)
    total_tokens = sum(len(t) for _, t in units)
    if total_frames == 0:
        raise SpeechError("The audio is empty.")
    frames_per_token = total_frames / total_tokens
    result: list[tuple[float, float, str]] = []
    cursor, i = 0, 0
    bar = tqdm(total=len(units), desc="Alignment", unit="sentence", disable=not progress)
    while i < len(units):
        j, letters = i, 0
        while j < len(units) and (j == i or letters + len(units[j][1]) <= GROUP_LETTERS):
            letters += len(units[j][1])
            j += 1
        last_group = j == len(units)
        expected = letters * frames_per_token
        end = total_frames if last_group else min(total_frames, cursor + int(expected * WINDOW_MARGIN) + WINDOW_EXTRA_FRAMES)
        while True:
            tokens = [t for _, toks in units[i:j] for t in toks]
            spans = _token_spans(emission[cursor:end], tokens)
            if spans is not None:
                break
            if end >= total_frames:
                # the text doesn't fit in what's left of the audio: the rest goes at the end
                raise SpeechError("The text is longer than its audio: is it the right chapter?")
            end = min(total_frames, cursor + 2 * (end - cursor))
        # times of each unit; all kept for the last group, all but the last otherwise (aligned again next time)
        keep = j - i if last_group or j - i == 1 else j - i - 1
        position = 0
        for k in range(i, i + keep):
            first, last = spans[position][0], spans[position + len(units[k][1]) - 1][1]
            result.append(((cursor + first) * FRAME_SECONDS, (cursor + last + 1) * FRAME_SECONDS, units[k][0]))
            position += len(units[k][1])
        cursor += spans[position - 1][1] + 1
        i += keep
        bar.update(keep)
    bar.close()
    return result


def _token_spans(log_probs: np.ndarray, tokens: list[int], blank: int = 0) -> list[tuple[int, int]] | None:
    """(first, last) frame of each token on the most likely CTC path (Viterbi), None when they don't fit."""
    frames, states = len(log_probs), 2 * len(tokens) + 1
    if not tokens or frames < len(tokens):
        return None
    labels = np.full(states, blank)
    labels[1::2] = tokens
    # a token can follow the one before it directly (skipping the blank) unless it's the same letter
    skip = np.zeros(states, dtype=bool)
    skip[3::2] = labels[3::2] != labels[1:-2:2]
    score = np.full(states, -np.inf)
    score[0], score[1] = log_probs[0, blank], log_probs[0, labels[1]]
    back = np.zeros((frames, states), dtype=np.int8)
    columns = np.arange(states)
    for t in range(1, frames):
        previous = np.concatenate(([-np.inf], score[:-1]))
        before = np.concatenate(([-np.inf, -np.inf], score[:-2]))
        before[~skip] = -np.inf
        candidates = np.stack([score, previous, before])
        choice = candidates.argmax(axis=0)
        score = candidates[choice, columns] + log_probs[t, labels]
        back[t] = choice
    state = states - 1 if score[-1] >= score[-2] else states - 2
    if not np.isfinite(score[state]):
        return None
    path = np.empty(frames, dtype=np.int64)
    for t in range(frames - 1, -1, -1):
        path[t] = state
        state -= int(back[t, state])
    spans: list[list[int]] = [[-1, -1] for _ in tokens]
    for t, s in enumerate(path):
        if s % 2:
            span = spans[s // 2]
            if span[0] < 0:
                span[0] = t
            span[1] = t
    return [tuple(s) for s in spans]
