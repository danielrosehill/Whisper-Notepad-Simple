# Whisper-Notepad-Simple

A simplified desktop application for recording audio, transcribing it with OpenAI's Whisper API, and optionally cleaning up the text with GPT.

## Features

- **Audio Recording**: Select your audio input device and record with simple controls
- **Whisper Transcription**: Transcribe your recordings using OpenAI's Whisper API
- **Optional Text Cleanup**: Apply basic text formatting and cleanup using GPT (can be toggled on/off)
- **Clipboard Integration**: Easily copy both raw and cleaned transcriptions
- **File Operations**: Save and load transcriptions

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/Whisper-Notepad-Simple.git
   cd Whisper-Notepad-Simple
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set your OpenAI API key:
   - Either set it as an environment variable: `export OPENAI_API_KEY=your-api-key`
   - Or enter it in the application via Settings > Set OpenAI API Key

## Usage

1. Run the application:
   ```
   python whisper_notepad_simple.py
   ```

2. Select your audio input device from the dropdown menu

3. Use the recording controls:
   - **Record**: Start recording audio
   - **Pause/Resume**: Pause or resume the current recording
   - **Stop**: Stop recording and prepare for transcription

4. Click **Transcribe** to process your recording with Whisper API

5. Toggle the **Apply Text Cleanup** checkbox to control whether GPT cleanup is applied to your transcription

6. Use the copy buttons to copy text to clipboard or save your notes using the Save button

## Requirements

- Python 3.8+
- PySide6
- sounddevice
- soundfile
- openai
- numpy

## License

This project is open source and available under the [MIT License](LICENSE).

## Acknowledgements

This is a simplified version of the original Whisper Notepad application, focused on core functionality.
