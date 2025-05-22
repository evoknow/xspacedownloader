# Translation in XSpace Downloader

This document explains how to set up and use the translation features in XSpace Downloader.

## Supported Languages

XSpace Downloader supports translation between the following languages:

- English (en)
- Spanish (es)
- French (fr)
- German (de)
- Italian (it)
- Portuguese (pt)
- Russian (ru)
- Chinese (zh)
- Japanese (ja)
- Arabic (ar)
- Bengali/Bangla (bn)

Additional languages may be available depending on your LibreTranslate setup.

## Setup Options

You have two options for enabling translation functionality:

### Option 1: Self-hosted LibreTranslate (Recommended)

This is the easiest and free option, using Python:

1. Run the provided setup script:
   ```bash
   ./setup_libretranslate_no_docker.sh
   ```

2. This will:
   - Create a Python virtual environment
   - Install LibreTranslate from PyPI
   - Configure XSpace to use the local server

3. After installation, start the server with:
   ```bash
   cd libretranslate
   source venv/bin/activate
   libretranslate --host localhost --port 5000
   ```

   Keep this terminal window open while using translation features.

3. Ensure `mainconfig.json` has these settings:
   ```json
   "translate": {
       "api_url": "https://libretranslate.com/translate",
       "api_key": "",
       "self_hosted": true,
       "self_hosted_url": "http://localhost:5000/translate"
   }
   ```

4. To manage the LibreTranslate server:
   - Stop: Press Ctrl+C in the terminal window
   - Start: Run the commands in step 3 again
   - When done, you can exit the virtual environment with `deactivate`

### Option 2: LibreTranslate API Key

If you prefer to use the hosted LibreTranslate service:

1. Get an API key from [LibreTranslate Portal](https://portal.libretranslate.com/)
2. Update `mainconfig.json` with your API key:
   ```json
   "translate": {
       "api_url": "https://libretranslate.com/translate",
       "api_key": "YOUR_API_KEY",
       "self_hosted": false
   }
   ```

## Using Translation Features

### In the Web Interface

1. Navigate to a space page that has a transcript
2. Select a target language from the dropdown next to the transcript
3. Click the "Translate" button
4. The transcript will be translated and displayed
5. Click "Show original" to revert to the original transcript

### Via API

```python
from components.Translate import Translate

# Create translator instance
translator = Translate()

# Translate text
success, result = translator.translate(
    text="Hello, how are you?",
    source_lang="en",
    target_lang="bn"  # Bengali/Bangla
)

if success:
    print(f"Translation: {result}")
else:
    print(f"Error: {result['error']}")
```

## Testing Translation

You can test the translation functionality using the provided test script:

```bash
./test_translation.py
```

If you're using a hosted LibreTranslate API, provide your API key:

```bash
./test_translation.py YOUR_API_KEY
```

## Troubleshooting

### Translation Not Working

If translation is not working:

1. Check if you're in self-hosted mode:
   - Ensure Docker is running
   - Check if the LibreTranslate container is running: `docker ps`
   - Test the API directly: `curl http://localhost:5000/languages`

2. If using an API key:
   - Verify your API key is correct
   - Check if you have exceeded API limits

### Adding More Languages

The default language list is defined in `components/Translate.py`. To add more languages:

1. Edit `components/Translate.py`
2. Add new language entries to the `self.available_languages` list
3. Update the dropdown in `templates/space.html` to include the new languages