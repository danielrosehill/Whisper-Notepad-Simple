# Voice-Notepad-With-Transformations

A desktop application for recording audio, transcribing it with Whisper (via OpenAI API), cleaning it up with GPT (via OpenAI API), and managing notes.

## Features

- Record audio from any connected microphone
- Automatically transcribe recordings using OpenAI's Whisper API
- Clean up transcriptions using OpenAI's GPT API
- Apply various text transformations to the transcriptions
- Save, load, and manage notes
- Copy cleaned text to clipboard

## Requirements

- Python 3.7+
- OpenAI API key (set as environment variable `OPENAI_API_KEY` or in the application settings)
- PySide6 (Qt for Python)
- Other dependencies listed in `requirements.txt`

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/Voice-Notepad-With-Transformations.git
   cd Voice-Notepad-With-Transformations
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set your OpenAI API key as an environment variable (optional, can also be set in the application):
   ```
   export OPENAI_API_KEY="your-api-key-here"
   ```

## Building a Standalone Executable

You can build a standalone executable using the included build script:

1. Make sure the build script is executable:
   ```
   chmod +x build.sh
   ```

2. Run the build script:
   ```
   ./build.sh
   ```

3. The executable will be created in the `dist` directory.

### Build Options

The build script supports several options:

```
Usage: ./build.sh [options]
Options:
  --dir                Build as directory instead of single file
  --file               Build as single file (default)
  --debug              Include debug information in build
  --no-clean           Don't clean up build files after completion
  --name=NAME          Specify output name (default: Voice-Notepad)
  --help               Show this help message
```

Examples:
```
# Build as a directory instead of a single file
./build.sh --dir

# Build with a custom name
./build.sh --name=MyVoiceNotepad

# Build with debug information and keep build files
./build.sh --debug --no-clean
```

## Usage

1. Run the application:
   ```
   python voice_notepad.py
   ```
   
   Or if you've built the executable:
   ```
   ./dist/Voice-Notepad
   ```

2. Select your preferred microphone from the dropdown menu.

3. Click the "Record" button to start recording.

4. Click the "Stop" button to stop recording. The application will automatically:
   - Transcribe the audio using Whisper
   - Clean up the transcription using GPT with the selected transformations

5. Use the note management buttons to:
   - Create a new note ("New Note")
   - Append the latest transcription to the existing note ("Append")
   - Save the note to a file ("Save")
   - Load a note from a file ("Load")

6. Use the "Copy to Clipboard" button to copy the cleaned transcription.

## Text Transformations

The application includes a variety of text transformations organized in categories:
- Basics (simple cleanup)
- Stylistic instructions (formalize, add emotion, etc.)
- Grammatical edits (first-person, third-person, etc.)
- Business formats
- And many more

Select one or more transformations to apply to your transcriptions. If no transformations are selected, the basic cleanup transformation will be applied by default.

## Configuration

The application saves your settings (API key, default microphone) to a configuration file located at `~/.voice_notepad_config.json`.

## License

[Insert your license information here]
