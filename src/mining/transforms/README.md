# Deinflection rules

These files come from [Yomitan](https://github.com/yomidevs/yomitan) (GPL-3.0-or-later): for each
language, the rules that bring an inflected word back to its dictionary form (食べなかった → 食べる,
mangeaient → manger, 먹었어요 → 먹다). They're read by `src/mining/deinflect.py`, a Python port of Yomitan's
`LanguageTransformer`.

To update them from a newer Yomitan:

```bash
git clone --depth 1 https://github.com/yomidevs/yomitan /tmp/yomitan
node tools/export_yomitan_transforms.mjs /tmp/yomitan src/mining/transforms
```

The few rules Yomitan writes as custom JavaScript functions (mostly German, English and Spanish
irregular forms) can't be stored as data and are skipped; the script prints how many.

Korean rules work on Hangul split into jamo (먹었다 → ㅁㅓㄱㅇㅓㅆㄷㅏ), like Yomitan does with Hangul.js:
`src/mining/hangul.py` is a port of it, applied around the rules by `deinflect.py`.
