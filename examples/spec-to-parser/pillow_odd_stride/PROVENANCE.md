# Provenance of the emitted spec

`requirements.md`, `design.md` and `test_pcx.py` in this folder are NECROPSY's
emitted spec for one real file, written by `emit_spec` at commit `a54b7ce` and
committed unedited.

- Source file: `spike/samples/real/pillow_odd_stride.pcx`, 14,313 bytes, from
  Pillow's test suite (`Tests/images/odd_stride.pcx`; origin and licence in
  `spike/samples/real/manifest.json`).
- Source sha256: `b7e6b331e9309e68e74f3daf11258976603b737b4b35e12a8a9fa5c7fd449a0d`

| file | sha256 |
|---|---|
| requirements.md | `9e8a1d6d4ddeb30290945c2021a1b098f52457e6d7b5e0488e5baabf90339efe` |
| design.md | `9a89c51aba6dcb0428259d5f784bee6fc2ec68ba3e34ea152016bd27f22bf386` |
| test_pcx.py | `0285a9e65dd646d48e7180d4f84e9fddb18f5c23859eec76ef7df1adc4ee8103` |

Regenerate and compare:

```
python -c "from pathlib import Path; from necropsy.engine import Engine; from necropsy.emit import emit_spec; d=Path('spike/samples/real/pillow_odd_stride.pcx').read_bytes(); [print(k, __import__('hashlib').sha256(v.encode()).hexdigest()) for k,v in dict(emit_spec(Engine().run(d), d).files).items()]"
```

The spec ships without a parser on purpose (Decision Record, emitted spec).
The parser in this folder, if present, was written afterwards by Kiro from
these three files alone.
