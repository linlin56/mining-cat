// Exports Yomitan's deinflection rules to JSON files read by src/mining/deinflect.py.
//
// Yomitan (https://github.com/yomidevs/yomitan, GPL-3.0-or-later) describes, for each language, how an
// inflected word goes back to its dictionary form (食べなかった -> 食べる). MiningCat reuses these rules
// instead of writing its own. Most rules replace a suffix, a prefix or a whole word, which can be
// stored as data; the few rules written as custom JavaScript functions are skipped and counted.
//
// Usage:
//   git clone --depth 1 https://github.com/yomidevs/yomitan /tmp/yomitan
//   node tools/export_yomitan_transforms.mjs /tmp/yomitan src/mining/transforms

import {mkdirSync, writeFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const [yomitanDir, outDir] = process.argv.slice(2);
if (!yomitanDir || !outDir) {
    console.error('usage: node export_yomitan_transforms.mjs <yomitan checkout> <output dir>');
    process.exit(1);
}

// language code -> [module path, exported name]
// Korean rules work on Hangul split into jamo (먹었다 -> ㅁㅓㄱㅇㅓㅆㄷㅏ): src/mining/hangul.py does the same split.
const LANGUAGES = {
    ja: ['ja/japanese-transforms.js', 'japaneseTransforms'],
    en: ['en/english-transforms.js', 'englishTransforms'],
    fr: ['fr/french-transforms.js', 'frenchTransforms'],
    de: ['de/german-transforms.js', 'germanTransforms'],
    es: ['es/spanish-transforms.js', 'spanishTransforms'],
    ko: ['ko/korean-transforms.js', 'koreanTransforms'],
};

const PROBE = '';

function unescapeRegex(source) {
    return source.replace(/\\(.)/g, '$1');
}

function isLiteral(text) {
    return !/[.*+?^${}()|[\]\\]/.test(text);
}

// Turns a rule into {kind, from, to}, or null when it can't be expressed as data.
function describeRule(rule) {
    const source = rule.isInflected.source;
    try {
        if (source.endsWith('$') && !source.startsWith('^')) {
            const from = unescapeRegex(source.slice(0, -1));
            if (!isLiteral(from)) { return null; }
            const to = typeof rule.deinflected === 'string' ? rule.deinflected : rule.deinflect(PROBE + from).slice(PROBE.length);
            if (rule.deinflect(PROBE + from) !== PROBE + to) { return null; }
            return {kind: 'suffix', from, to};
        }
        if (source.startsWith('^') && source.endsWith('$')) {
            const from = unescapeRegex(source.slice(1, -1));
            if (!isLiteral(from)) { return null; }
            const to = rule.deinflect(from);
            if (rule.deinflect(from + 'x') !== to) { return null; }  // must not depend on the input
            return {kind: 'whole', from, to};
        }
        if (source.startsWith('^')) {
            const from = unescapeRegex(source.slice(1));
            if (!isLiteral(from)) { return null; }
            const out = rule.deinflect(from + PROBE);
            if (!out.endsWith(PROBE)) { return null; }
            return {kind: 'prefix', from, to: out.slice(0, -PROBE.length)};
        }
    } catch {
        return null;
    }
    return null;
}

mkdirSync(outDir, {recursive: true});
const languageDir = join(resolve(yomitanDir), 'ext/js/language');
for (const [lang, [path, name]] of Object.entries(LANGUAGES)) {
    const module = await import(pathToFileURL(join(languageDir, path)).href);
    const descriptor = module[name];
    const transforms = {};
    let kept = 0;
    let skipped = 0;
    for (const [id, transform] of Object.entries(descriptor.transforms)) {
        const rules = [];
        for (const rule of transform.rules) {
            const described = describeRule(rule);
            if (described === null) { ++skipped; continue; }
            rules.push({...described, conditionsIn: rule.conditionsIn, conditionsOut: rule.conditionsOut});
            ++kept;
        }
        if (rules.length > 0) {
            transforms[id] = {name: transform.name, description: transform.description || '', rules};
        }
    }
    const conditions = {};
    for (const [type, condition] of Object.entries(descriptor.conditions)) {
        conditions[type] = {
            name: condition.name,
            isDictionaryForm: Boolean(condition.isDictionaryForm),
            subConditions: condition.subConditions || [],
        };
    }
    const data = {
        language: lang,
        source: 'Exported from Yomitan (https://github.com/yomidevs/yomitan), GPL-3.0-or-later, by tools/export_yomitan_transforms.mjs',
        conditions,
        transforms,
    };
    writeFileSync(join(outDir, `${lang}.json`), JSON.stringify(data, null, 1) + '\n');
    console.log(`${lang}: ${kept} rules exported, ${skipped} custom rules skipped`);
}
