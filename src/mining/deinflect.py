import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

TRANSFORMS_DIR = Path(__file__).parent / "transforms"

# Guards against pathological rule chains.
MAX_RESULTS = 2000


@dataclass(frozen=True)
class Rule:
    kind: str          # suffix, prefix or whole
    source: str        # inflected part
    target: str        # deinflected part
    conditions_in: int
    conditions_out: int


@dataclass
class Transform:
    id: str
    name: str
    description: str
    rules: list[Rule]


@dataclass(frozen=True)
class Deinflection:
    text: str
    conditions: int
    trace: tuple[str, ...] = field(default=())  # transform ids, from the outermost inflection inward


class LanguageTransformer:
    # `preprocess` / `postprocess`: what Yomitan's text processors do around the rules (Korean rules work on jamo).
    def __init__(self, descriptor: dict, preprocess=None, postprocess=None):
        self._preprocess = preprocess
        self._postprocess = postprocess
        self._condition_flags = self._build_condition_flags(descriptor["conditions"])
        self._pos_flags = {
            name: flags for name, flags in self._condition_flags.items()
            if descriptor["conditions"][name].get("isDictionaryForm")
        }
        self.transforms: list[Transform] = []
        for transform_id, transform in descriptor["transforms"].items():
            rules = [
                Rule(
                    kind=r["kind"], source=r["from"], target=r["to"],
                    conditions_in=self._flags(r["conditionsIn"]),
                    conditions_out=self._flags(r["conditionsOut"]),
                )
                for r in transform["rules"]
            ]
            self.transforms.append(Transform(transform_id, transform["name"], transform.get("description", ""), rules))
        # Suffix rules indexed by their last character: most texts only need a handful of checks.
        self._by_last_char: dict[str, list[tuple[Transform, Rule]]] = {}
        self._other: list[tuple[Transform, Rule]] = []
        for transform in self.transforms:
            for rule in transform.rules:
                if rule.kind == "suffix" and rule.source:
                    self._by_last_char.setdefault(rule.source[-1], []).append((transform, rule))
                else:
                    self._other.append((transform, rule))

    @staticmethod
    def _build_condition_flags(conditions: dict) -> dict[str, int]:
        flags: dict[str, int] = {}
        next_bit = 0

        def resolve(name: str, stack: tuple = ()) -> int:
            nonlocal next_bit
            if name in flags:
                return flags[name]
            if name in stack:
                raise ValueError(f"Cycle in conditions at {name}")
            subs = conditions[name].get("subConditions") or []
            if subs:
                value = 0
                for sub in subs:
                    value |= resolve(sub, stack + (name,))
            else:
                value = 1 << next_bit
                next_bit += 1
            flags[name] = value
            return value

        for name in conditions:
            resolve(name)
        return flags

    def _flags(self, names: list[str]) -> int:
        value = 0
        for name in names:
            value |= self._condition_flags.get(name, 0)
        return value

    def flags_for_parts_of_speech(self, parts_of_speech: list[str]) -> int:
        value = 0
        for pos in parts_of_speech:
            value |= self._pos_flags.get(pos, 0)
        return value

    @staticmethod
    def conditions_match(current: int, required: int) -> bool:
        return current == 0 or (current & required) != 0

    def _candidates(self, text: str):
        if text:
            yield from self._by_last_char.get(text[-1], ())
        yield from self._other

    def transform(self, text: str) -> list[Deinflection]:
        if self._preprocess is None:
            return self._transform(text)
        results = self._transform(self._preprocess(text))
        return [Deinflection(self._postprocess(d.text), d.conditions, d.trace) for d in results]

    def _transform(self, text: str) -> list[Deinflection]:
        results = [Deinflection(text, 0, ())]
        seen = {(text, 0)}
        i = 0
        while i < len(results) and len(results) < MAX_RESULTS:
            current = results[i]
            i += 1
            for transform, rule in self._candidates(current.text):
                if not self.conditions_match(current.conditions, rule.conditions_in):
                    continue
                if rule.kind == "suffix":
                    if not current.text.endswith(rule.source):
                        continue
                    new_text = current.text[: len(current.text) - len(rule.source)] + rule.target
                elif rule.kind == "prefix":
                    if not current.text.startswith(rule.source):
                        continue
                    new_text = rule.target + current.text[len(rule.source):]
                else:
                    if current.text != rule.source:
                        continue
                    new_text = rule.target
                key = (new_text, rule.conditions_out)
                if key in seen or not new_text:
                    continue
                seen.add(key)
                results.append(Deinflection(new_text, rule.conditions_out, current.trace + (transform.id,)))
        return results

    def describe(self, trace: tuple[str, ...]) -> list[dict]:
        by_id = {t.id: t for t in self.transforms}
        return [
            {"name": by_id[t].name, "description": by_id[t].description} if t in by_id else {"name": t}
            for t in trace
        ]


@lru_cache(maxsize=None)
def transformer_for(language: str) -> LanguageTransformer | None:
    path = TRANSFORMS_DIR / f"{language}.json"
    if not path.exists():
        return None
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    if language == "ko":
        from miningcat.domain.text.hangul import assemble, disassemble
        return LanguageTransformer(descriptor, disassemble, assemble)
    return LanguageTransformer(descriptor)
