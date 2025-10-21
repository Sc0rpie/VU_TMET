Darbą atliko huvi8958 ir olra8878

Grąžinamas default.char, kai kodas (cp) patenka į atmetimo diapazoną.

```bash
python3 interpreter.py interp Sample14.trm --family dialog --cp 0x0101
```

Kai kodas (cp) didesnis nei 0x00ff, jis nebepriklauso ANSI_CHARSET simbolių rinkiniui, todėl bandomas sekantis šriftas, kuris nėra ANSI_CHARSET.

```bash
python3 interpreter.py interp Sample14.trm --family dialog --cp 0x0100
```
