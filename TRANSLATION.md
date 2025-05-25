# Translation in XSpace Downloader

This document explains how to set up and use the translation features in XSpace Downloader.

## Overview

XSpace Downloader uses AI-powered translation services (OpenAI or Claude) to provide high-quality translations of space transcripts.

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
- Hindi (hi)
- Korean (ko)
- Dutch (nl)
- Swedish (sv)
- Turkish (tr)

## Setup

Translation uses the same AI configuration as transcription. Configure your AI provider in `mainconfig.json`:

### Option 1: OpenAI

```json
{
    "translate": {
        "enable": true,
        "provider": "openai",
        "openai": {
            "api_key": "your-openai-api-key",
            "model": "gpt-4o"
        }
    }
}
```

### Option 2: Claude

```json
{
    "translate": {
        "enable": true,
        "provider": "claude",
        "claude": {
            "api_key": "your-anthropic-api-key",
            "model": "claude-3-sonnet-20240229"
        }
    }
}
```

## Using Translation

1. **In the Web Interface**:
   - Navigate to a space page
   - View the transcript
   - Select your target language from the dropdown
   - Click the translate button

2. **Features**:
   - Translations are cached in the database
   - Long texts are automatically split into chunks
   - Progress is shown during translation
   - You can switch between original and translated text

## API Endpoints

- `POST /api/translate` - Translate text
- `GET /api/translate/check` - Check translation service status
- `GET /api/languages` - Get supported languages

## Notes

- Translation quality depends on your AI provider
- Costs may apply based on your API usage
- Translations are stored in the database for quick access