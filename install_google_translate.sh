#!/bin/bash
# Install the googletrans package for simple translation

if [ -d "libretranslate/venv" ]; then
    echo "Using existing virtual environment..."
    source libretranslate/venv/bin/activate
else
    echo "Creating new virtual environment..."
    python -m venv venv
    source venv/bin/activate
fi

echo "Installing googletrans package..."
pip install googletrans==4.0.0-rc1

echo ""
echo "Installation complete!"
echo ""
echo "To use the translator, run:"
echo ""
echo "python simple_google_translate.py 'Hello world' es"
echo ""
echo "This will translate 'Hello world' to Spanish"