# Using Translation in XSpace Downloader

## Direct Translation with libretranslatepy

The easiest way to use translation is with the included quick_translate.py script which uses the libretranslatepy library directly without needing a server:

```bash
# Example: Translate text to Spanish
./quick_translate.py --text "Hello, how are you today?" --target es

# Example: Translate from French to English
./quick_translate.py --text "Bonjour, comment allez-vous?" --source fr --target en

# Example: Auto-detect source language
./quick_translate.py --text "Hola, ¿cómo estás hoy?" --target en
```

## Web Application Translation

The web application should automatically use the libretranslatepy library directly, without needing a server. This works with the default configuration:

```json
"translate": {
    "api_url": "http://localhost:5000/translate",
    "api_key": "",
    "self_hosted": true,
    "self_hosted_url": "http://localhost:5000/translate",
    "comment": "Using local LibreTranslate server with libretranslatepy"
}
```

## Supported Languages

The libretranslatepy library supports these languages:
- English (en)
- Arabic (ar)
- Azerbaijani (az)
- Chinese (zh)
- Czech (cs)
- Danish (da)
- Dutch (nl)
- Esperanto (eo)
- Finnish (fi)
- French (fr)
- German (de)
- Greek (el)
- Hebrew (he)
- Hindi (hi)
- Hungarian (hu)
- Indonesian (id)
- Irish (ga)
- Italian (it)
- Japanese (ja)
- Korean (ko)
- Persian (fa)
- Polish (pl)
- Portuguese (pt)
- Russian (ru)
- Slovak (sk)
- Spanish (es)
- Swedish (sv)
- Turkish (tr)
- Ukrainian (uk)

Note: Support for Bengali/Bangla (bn) depends on the installed language models.