#!/usr/bin/env python3
"""
AI Voice Note Optimizer

A desktop application for recording audio, transcribing it with Whisper (via OpenAI API),
cleaning it up with GPT (via OpenAI API), and managing notes with advanced transformation options.

Dependencies:
- PySide6: Qt bindings for Python
- sounddevice: Audio recording
- soundfile: Audio file I/O
- openai: OpenAI API client
- numpy: Array manipulation (used with sounddevice)
- json: For configuration file handling
- os: For file and environment variable operations
- glob: For finding transformation files
"""

import sys
import os
import json
import glob
import time
import tempfile
import threading
from pathlib import Path
from datetime import datetime

import numpy as np
import sounddevice as sd
import soundfile as sf
import openai

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QTextEdit, QComboBox,
    QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QMessageBox, QGroupBox,
    QScrollArea, QCheckBox, QGridLayout, QSplitter, QFrame
)
from PySide6.QtCore import Qt, QSettings, QTimer, Signal, QObject, Slot
from PySide6.QtGui import QIcon, QFont, QAction, QClipboard, QFontMetrics

# Constants
APP_NAME = "AI Voice Note Optimizer"
CONFIG_FILE = os.path.expanduser("~/.voice_notepad_config.json")
SYSTEM_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system-prompts")


class RecordingThread(QObject):
    """Thread for handling audio recording to avoid UI freezing."""
    finished = Signal()
    error = Signal(str)
    
    def __init__(self, device, sample_rate=16000, channels=1):
        super().__init__()
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self.paused = False
        self.frames = []
        self.current_chunk = []
        self.chunk_files = []
        self.recording_duration = 0
        self.start_time = time.time()
        
        # Create a temporary directory for chunks
        self.temp_dir = tempfile.mkdtemp()
        
    def get_supported_sample_rate(self, device_id):
        """Get a supported sample rate for the device."""
        try:
            # Try to get device info
            device_info = sd.query_devices(device_id, 'input')
            
            # Common sample rates to try, in order of preference
            common_rates = [48000, 44100, 16000, 8000]
            
            # If device has a default sample rate, use it
            if device_info and 'default_samplerate' in device_info:
                default_rate = int(device_info['default_samplerate'])
                return default_rate
            
            # Otherwise try common rates
            for rate in common_rates:
                try:
                    # Test if this sample rate works with the device
                    sd.check_input_settings(device=device_id, samplerate=rate, channels=self.channels)
                    return rate
                except:
                    continue
                    
            # If no common rates work, return the lowest as a last resort
            return 8000
        except Exception as e:
            print(f"Error determining supported sample rate: {e}")
            return 16000  # Default fallback
        
    def start_recording(self):
        """Start recording audio from the selected device."""
        self.recording = True
        self.paused = False
        self.frames = []
        self.current_chunk = []
        self.chunk_files = []
        self.recording_duration = 0
        self.start_time = time.time()
        
        def callback(indata, frames, time_info, status):
            if status:
                print(f"Status: {status}")
            if self.recording and not self.paused:
                self.current_chunk.append(indata.copy())
                
                # Calculate recording duration and emit progress
                current_time = time.time()
                self.recording_duration = current_time - self.start_time
                
                # Check if current chunk has reached chunk_size
                chunk_duration = len(self.current_chunk) * frames / self.sample_rate
                if chunk_duration >= 60:  # 1 minute chunks
                    self._save_current_chunk()
        
        try:
            # Get a supported sample rate for this device
            self.sample_rate = self.get_supported_sample_rate(self.device)
            print(f"Using sample rate: {self.sample_rate}")
            
            self.stream = sd.InputStream(
                device=self.device,
                channels=self.channels,
                samplerate=self.sample_rate,
                callback=callback
            )
            self.stream.start()
        except Exception as e:
            self.error.emit(f"Error starting recording: {str(e)}")
            
    def pause_recording(self):
        """Pause the recording without stopping it."""
        self.paused = True
        
    def resume_recording(self):
        """Resume a paused recording."""
        self.paused = False
            
    def stop_recording(self):
        """Stop recording and save the audio to a temporary file."""
        if hasattr(self, 'stream'):
            self.recording = False
            self.paused = False
            self.stream.stop()
            self.stream.close()
            
            try:
                # Save the final chunk if there's any data
                if self.current_chunk:
                    self._save_current_chunk()
                
                # Create a temporary file for the complete recording
                fd, temp_path = tempfile.mkstemp(suffix='.wav')
                os.close(fd)
                
                if self.chunk_files:
                    # Combine all chunks into a single file
                    combined_data = None
                    
                    for chunk_file in self.chunk_files:
                        data, _ = sf.read(chunk_file)
                        if combined_data is None:
                            combined_data = data
                        else:
                            combined_data = np.concatenate((combined_data, data))
                    
                    # Save as WAV file
                    if combined_data is not None and len(combined_data) > 0:
                        # Check if audio is long enough (at least 0.5 seconds)
                        min_duration_samples = int(0.5 * self.sample_rate)
                        if len(combined_data) < min_duration_samples:
                            # Pad with silence if needed
                            silence_pad = np.zeros((min_duration_samples - len(combined_data), self.channels))
                            combined_data = np.concatenate((combined_data, silence_pad))
                            
                        sf.write(temp_path, combined_data, self.sample_rate)
                        self.temp_file_path = temp_path
                        self.finished.emit()
                    else:
                        self.error.emit("No audio recorded or recording too short")
                        
                    # Clean up chunk files
                    for chunk_file in self.chunk_files:
                        try:
                            os.remove(chunk_file)
                        except:
                            pass
                    try:
                        os.rmdir(self.temp_dir)
                    except:
                        pass
                else:
                    self.error.emit("No audio recorded")
            except Exception as e:
                self.error.emit(f"Error saving recording: {str(e)}")
        else:
            self.error.emit("No recording stream found")
    
    def _save_current_chunk(self):
        """Save the current chunk to a temporary file."""
        chunk_path = os.path.join(self.temp_dir, f"chunk_{len(self.chunk_files)}.wav")
        sf.write(chunk_path, np.concatenate(self.current_chunk), self.sample_rate)
        self.chunk_files.append(chunk_path)
        self.current_chunk = []


class TranscriptionThread(QObject):
    """Thread for handling audio transcription to avoid UI freezing."""
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(str)
    
    def __init__(self, audio_file_path):
        super().__init__()
        self.audio_file_path = audio_file_path
        
    def transcribe(self):
        """Transcribe the audio file using OpenAI's Whisper API."""
        try:
            # Check if API key is set
            if not openai.api_key:
                self.error.emit("OpenAI API key is not set. Please set it in Settings > Set OpenAI API Key.")
                return
                
            # Check if file exists and has content
            if not os.path.exists(self.audio_file_path):
                self.error.emit(f"Audio file not found: {self.audio_file_path}")
                return
                
            file_size = os.path.getsize(self.audio_file_path)
            if file_size == 0:
                self.error.emit("Audio file is empty. No audio was recorded.")
                return
            
            # Check audio duration to ensure it's long enough
            try:
                audio_data, sample_rate = sf.read(self.audio_file_path)
                duration = len(audio_data) / sample_rate
                if duration < 0.5:  # Less than half a second
                    self.error.emit("Audio file is too short for transcription (less than 0.5 seconds)")
                    return
            except Exception as e:
                print(f"Warning: Could not check audio duration: {e}")
            
            # Check if file is too large for direct API upload (limit is 25MB)
            MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB in bytes
            
            if file_size > MAX_FILE_SIZE:
                self.progress.emit("File is large, splitting into chunks for transcription...")
                # Split the audio file into chunks
                transcript = self._transcribe_large_file()
            else:
                # Regular transcription for smaller files
                with open(self.audio_file_path, "rb") as audio_file:
                    self.progress.emit("Transcribing audio...")
                    transcript = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                    
                # Check if transcript has content
                if not transcript or not hasattr(transcript, 'text') or not transcript.text:
                    self.error.emit("Received empty transcript from OpenAI API.")
                    return
                    
                transcript = transcript.text
                
            self.finished.emit(transcript)
        except Exception as e:
            self.error.emit(f"Error during transcription: {str(e)}")
    
    def _transcribe_large_file(self):
        """Handle transcription of large audio files by splitting into chunks."""
        try:
            import librosa
            
            # Load the audio file
            self.progress.emit("Loading audio file...")
            y, sr = librosa.load(self.audio_file_path, sr=None)
            
            # Calculate duration in seconds
            duration = librosa.get_duration(y=y, sr=sr)
            
            # Check if audio is too short
            if duration < 0.5:
                self.error.emit("Audio file is too short for transcription (less than 0.5 seconds)")
                return ""
            
            # Determine chunk size (in seconds)
            chunk_duration = 60  # 1 minute chunks
            
            # Calculate number of chunks
            num_chunks = int(np.ceil(duration / chunk_duration))
            
            self.progress.emit(f"Processing {num_chunks} chunks...")
            
            # Process each chunk
            transcripts = []
            
            for i in range(num_chunks):
                self.progress.emit(f"Transcribing chunk {i+1}/{num_chunks}...")
                
                # Calculate start and end samples for this chunk
                start_sample = int(i * chunk_duration * sr)
                end_sample = int(min((i + 1) * chunk_duration * sr, len(y)))
                
                # Extract chunk
                chunk = y[start_sample:end_sample]
                
                # Ensure chunk is long enough (at least 0.5 seconds)
                min_samples = int(0.5 * sr)
                if len(chunk) < min_samples:
                    # Pad with silence if needed
                    silence_pad = np.zeros(min_samples - len(chunk))
                    chunk = np.concatenate((chunk, silence_pad))
                
                # Save chunk to temporary file
                chunk_path = os.path.join(tempfile.gettempdir(), f"chunk_{i}.wav")
                sf.write(chunk_path, chunk, sr)
                
                # Transcribe chunk
                with open(chunk_path, "rb") as audio_file:
                    chunk_transcript = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                
                # Add to transcripts
                if chunk_transcript and hasattr(chunk_transcript, 'text') and chunk_transcript.text:
                    transcripts.append(chunk_transcript.text)
                
                # Clean up temporary file
                try:
                    os.remove(chunk_path)
                except:
                    pass
            
            # Combine all transcripts
            return " ".join(transcripts)
            
        except ImportError:
            self.error.emit("librosa library is required for processing large audio files. Please install it with: pip install librosa")
            return ""
        except Exception as e:
            self.error.emit(f"Error processing large audio file: {str(e)}")
            return ""


class CleanupThread(QObject):
    """Thread for handling text cleanup with GPT to avoid UI freezing."""
    finished = Signal(str)
    error = Signal(str)
    
    def __init__(self, text, system_prompt):
        super().__init__()
        self.text = text
        self.system_prompt = system_prompt
        
    def cleanup(self):
        """Clean up the transcription using OpenAI's GPT API."""
        try:
            # Check if API key is set
            if not openai.api_key:
                self.error.emit("OpenAI API key is not set. Please set it in Settings > Set OpenAI API Key.")
                return
                
            # Check if text is empty
            if not self.text:
                self.error.emit("No text to clean up.")
                return
            
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self.text}
                ]
            )
            
            # Check if response has content
            if not response or not response.choices or not response.choices[0].message.content:
                self.error.emit("Received empty response from OpenAI API.")
                return
                
            cleaned_text = response.choices[0].message.content
            self.finished.emit(cleaned_text)
        except Exception as e:
            self.error.emit(f"Error during GPT cleanup: {str(e)}")


class TransformationManager:
    """Manages text transformation prompts from the system-prompts directory."""
    
    def __init__(self, prompts_dir):
        self.prompts_dir = prompts_dir
        self.categories = {}
        self.transformation_stacks = {}
        self.load_transformations()
        
    def load_transformations(self):
        """Load all transformation files from the system-prompts directory."""
        # First, check for a default.md file in the root directory
        default_file = os.path.join(self.prompts_dir, "default.md")
        if os.path.exists(default_file):
            default_transformation = self._parse_transformation_file(default_file)
            if default_transformation:
                # Create a special category for the default transformation
                self.categories["default"] = [default_transformation]
                print(f"Loaded default system prompt from {default_file}")
        
        # Get all directories (categories) in the prompts directory
        category_dirs = [d for d in os.listdir(self.prompts_dir) 
                        if os.path.isdir(os.path.join(self.prompts_dir, d))]
        
        for category in category_dirs:
            category_path = os.path.join(self.prompts_dir, category)
            # Get all markdown files in the category directory
            md_files = glob.glob(os.path.join(category_path, "*.md"))
            
            transformations = []
            for md_file in md_files:
                transformation = self._parse_transformation_file(md_file)
                if transformation:
                    transformations.append(transformation)
            
            if transformations:
                self.categories[category] = transformations
    
    def _parse_transformation_file(self, file_path):
        """Parse a transformation file to extract title, description, and prompt."""
        try:
            with open(file_path, "r") as f:
                content = f.read()
            
            # Extract filename without extension as a fallback title
            filename = os.path.basename(file_path)
            name = os.path.splitext(filename)[0]
            
            # Try to extract title from markdown heading
            title = name
            if content.startswith("# "):
                title_line = content.split("\n")[0]
                title = title_line.replace("# ", "").strip()
            
            # Try to extract description
            description = ""
            desc_start = content.find("## Description")
            if desc_start != -1:
                desc_end = content.find("##", desc_start + 1)
                if desc_end == -1:
                    desc_end = content.find("```", desc_start)
                if desc_end != -1:
                    description = content[desc_start + 14:desc_end].strip()
            
            # Extract prompt
            prompt = ""
            prompt_start = content.find("```", content.find("## Prompt"))
            if prompt_start != -1:
                prompt_end = content.find("```", prompt_start + 3)
                if prompt_end != -1:
                    prompt = content[prompt_start + 3:prompt_end].strip()
            
            return {
                "id": name,
                "title": title,
                "description": description,
                "prompt": prompt,
                "file_path": file_path
            }
        except Exception as e:
            print(f"Error parsing transformation file {file_path}: {str(e)}")
            return None
    
    def get_categories(self):
        """Get all available transformation categories."""
        return list(self.categories.keys())
    
    def get_transformations_for_category(self, category):
        """Get all transformations for a specific category."""
        return self.categories.get(category, [])
    
    def get_default_transformations(self):
        """Get the default transformations (from the 'default' category or 'basics' category)."""
        # First check if we have a dedicated default transformation
        if "default" in self.categories:
            return self.categories["default"]
        # Fall back to basics category
        return self.categories.get("basics", [])
    
    def get_combined_prompt(self, selected_transformations):
        """Combine multiple transformation prompts into a single system prompt."""
        # If no transformations are selected, use the default transformation
        if not selected_transformations:
            # First try to use the default category
            if "default" in self.categories:
                return self.categories["default"][0]["prompt"]
            # Fall back to basics category if no default
            elif "basics" in self.categories:
                basics = self.categories["basics"]
                if basics:
                    return basics[0]["prompt"]
                
        # Start with an empty prompt
        combined_prompt = ""
        
        # Add selected transformation prompts
        for transformation in selected_transformations:
            # Add a separator if we already have content
            if combined_prompt:
                combined_prompt += "\n\n"
                
            combined_prompt += transformation["prompt"]
        
        # If still empty, use a fallback basic cleanup prompt
        if not combined_prompt:
            combined_prompt = "You are a text cleanup assistant. Clean up the text by fixing grammar, spelling, and punctuation errors."
            
        return combined_prompt.strip()
    
    def save_transformation_stack(self, name, transformations):
        """Save a named stack of transformations."""
        self.transformation_stacks[name] = transformations.copy()
        return True
        
    def get_transformation_stack(self, name):
        """Get a named stack of transformations."""
        return self.transformation_stacks.get(name, [])
        
    def get_all_transformation_stacks(self):
        """Get all saved transformation stacks."""
        return self.transformation_stacks
        
    def delete_transformation_stack(self, name):
        """Delete a named transformation stack."""
        if name in self.transformation_stacks:
            del self.transformation_stacks[name]
            return True
        return False


class VoiceNotepadApp(QMainWindow):
    """Main application window for AI Voice Note Optimizer."""
    
    def __init__(self):
        super().__init__()
        self.recording_thread = None
        self.transcription_thread = None
        self.cleanup_thread = None
        self.temp_audio_file = None
        self.selected_transformations = []
        self.skip_transformations = False
        self.basic_transformations_only = False
        
        # Load configuration
        self.load_config()
        
        # Initialize OpenAI API
        openai.api_key = self.config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
        
        # Initialize transformation manager
        self.transformation_manager = TransformationManager(SYSTEM_PROMPTS_DIR)
        
        # Set up the UI
        self.init_ui()
        
        # Load available audio devices
        self.load_audio_devices()
        
        # Load transformation stacks from config
        self.load_transformation_stacks()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1000, 800)
        
        # Create central widget and main layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Create top section with audio controls
        top_section = QWidget()
        top_layout = QHBoxLayout(top_section)
        
        # Audio device selection
        device_group = QGroupBox("Audio Device")
        device_layout = QVBoxLayout(device_group)
        self.device_combo = QComboBox()
        device_layout.addWidget(self.device_combo)
        top_layout.addWidget(device_group)
        
        # Recording controls
        recording_group = QGroupBox("Recording")
        recording_layout = QHBoxLayout(recording_group)
        
        # Record button with icon
        self.record_button = QPushButton()
        self.record_button.setIcon(QIcon.fromTheme("media-record", QIcon.fromTheme("media-playback-start")))
        self.record_button.setToolTip("Start Recording")
        self.record_button.clicked.connect(self.start_recording)
        
        # Pause button with icon
        self.pause_button = QPushButton()
        self.pause_button.setIcon(QIcon.fromTheme("media-playback-pause"))
        self.pause_button.setToolTip("Pause Recording")
        self.pause_button.clicked.connect(self.pause_recording)
        self.pause_button.setEnabled(False)
        
        # Stop button with icon
        self.stop_button = QPushButton()
        self.stop_button.setIcon(QIcon.fromTheme("media-playback-stop"))
        self.stop_button.setToolTip("Stop Recording")
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.setEnabled(False)
        
        recording_layout.addWidget(self.record_button)
        recording_layout.addWidget(self.pause_button)
        recording_layout.addWidget(self.stop_button)
        top_layout.addWidget(recording_group)
        
        # Process controls
        process_group = QGroupBox("Processing")
        process_layout = QHBoxLayout(process_group)
        
        # Transcribe button
        self.transcribe_button = QPushButton("Transcribe")
        self.transcribe_button.setToolTip("Transcribe the recorded audio")
        self.transcribe_button.clicked.connect(self.transcribe_audio)
        self.transcribe_button.setEnabled(False)
        
        # Basic Cleanup button
        self.basic_cleanup_button = QPushButton("Basic Cleanup")
        self.basic_cleanup_button.setToolTip("Apply basic text cleanup")
        self.basic_cleanup_button.clicked.connect(self.basic_cleanup)
        self.basic_cleanup_button.setEnabled(False)
        
        # Cleanup with Transformations button
        self.transform_cleanup_button = QPushButton("Cleanup with Transformations")
        self.transform_cleanup_button.setToolTip("Apply cleanup with selected transformations")
        self.transform_cleanup_button.clicked.connect(self.cleanup_with_transformations)
        self.transform_cleanup_button.setEnabled(False)
        
        # Clear button
        self.clear_button = QPushButton("Clear All")
        self.clear_button.setToolTip("Clear all transcripts")
        self.clear_button.clicked.connect(self.new_note)
        
        process_layout.addWidget(self.transcribe_button)
        process_layout.addWidget(self.basic_cleanup_button)
        process_layout.addWidget(self.transform_cleanup_button)
        process_layout.addWidget(self.clear_button)
        top_layout.addWidget(process_group)
        
        main_layout.addWidget(top_section)
        
        # Create middle section with transcription areas
        middle_section = QSplitter(Qt.Vertical)
        
        # Raw transcription area
        raw_group = QGroupBox("Raw Transcription")
        raw_layout = QVBoxLayout(raw_group)
        
        # Set larger font for the group box title
        raw_font = raw_group.font()
        raw_font.setPointSize(raw_font.pointSize() + 2)
        raw_font.setBold(True)
        raw_group.setFont(raw_font)
        
        # Add copy button for raw text
        raw_top_layout = QHBoxLayout()
        self.raw_copy_button = QPushButton()
        self.raw_copy_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.raw_copy_button.setToolTip("Copy to Clipboard")
        self.raw_copy_button.clicked.connect(lambda: self.copy_text_to_clipboard(self.raw_text))
        raw_top_layout.addStretch()
        raw_top_layout.addWidget(self.raw_copy_button)
        raw_layout.addLayout(raw_top_layout)
        
        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        raw_layout.addWidget(self.raw_text)
        middle_section.addWidget(raw_group)
        
        # GPT-cleaned transcription area
        cleaned_group = QGroupBox("Clean Transcription")
        cleaned_layout = QVBoxLayout(cleaned_group)
        
        # Set larger font for the group box title
        cleaned_font = cleaned_group.font()
        cleaned_font.setPointSize(cleaned_font.pointSize() + 2)
        cleaned_font.setBold(True)
        cleaned_group.setFont(cleaned_font)
        
        # Add copy button for cleaned text
        cleaned_top_layout = QHBoxLayout()
        self.copy_button = QPushButton()
        self.copy_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_button.setToolTip("Copy to Clipboard")
        self.copy_button.clicked.connect(lambda: self.copy_text_to_clipboard(self.cleaned_text))
        cleaned_top_layout.addStretch()
        cleaned_top_layout.addWidget(self.copy_button)
        cleaned_layout.addLayout(cleaned_top_layout)
        
        self.cleaned_text = QTextEdit()
        cleaned_layout.addWidget(self.cleaned_text)
        
        middle_section.addWidget(cleaned_group)
        
        main_layout.addWidget(middle_section, 1)  # Give it a stretch factor of 1
        
        # Create bottom section with transformations
        bottom_section = QGroupBox("Text Transformations")
        bottom_layout = QVBoxLayout(bottom_section)
        
        # Add transformation options
        transformation_options_layout = QHBoxLayout()
        
        # Transformation stack selector
        transformation_options_layout.addWidget(QLabel("Transformation Stack:"))
        self.stack_combo = QComboBox()
        self.stack_combo.setMinimumWidth(200)
        self.update_stack_combo()
        transformation_options_layout.addWidget(self.stack_combo)
        
        # Apply stack button
        self.apply_stack_button = QPushButton("Apply Stack")
        self.apply_stack_button.clicked.connect(self.apply_transformation_stack)
        transformation_options_layout.addWidget(self.apply_stack_button)
        
        # Save stack button
        self.save_stack_button = QPushButton("Save Current as Stack")
        self.save_stack_button.clicked.connect(self.save_current_as_stack)
        transformation_options_layout.addWidget(self.save_stack_button)
        
        # Delete stack button
        self.delete_stack_button = QPushButton("Delete Stack")
        self.delete_stack_button.clicked.connect(self.delete_transformation_stack)
        transformation_options_layout.addWidget(self.delete_stack_button)
        
        bottom_layout.addLayout(transformation_options_layout)
        
        # Add a description label
        description_label = QLabel("Select transformations to apply to the transcribed text:")
        bottom_layout.addWidget(description_label)
        
        # Create a scroll area for transformations
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Create accordion layout for transformation categories
        self.transformation_widgets = {}
        self.category_frames = {}
        
        # Get all transformation categories
        categories = self.transformation_manager.get_categories()
        categories.sort()  # Sort alphabetically
        
        # Create a section for each category
        for category in categories:
            # Skip the default category as it's applied automatically
            if category == "default":
                continue
                
            # Create collapsible section
            category_frame = QFrame()
            category_frame.setFrameShape(QFrame.StyledPanel)
            category_frame.setFrameShadow(QFrame.Raised)
            
            category_layout = QVBoxLayout(category_frame)
            category_layout.setContentsMargins(0, 0, 0, 0)
            
            # Header with toggle button
            header_layout = QHBoxLayout()
            toggle_button = QPushButton("+")
            toggle_button.setMaximumWidth(30)
            header_layout.addWidget(toggle_button)
            
            # Category title
            title_label = QLabel(category.replace("-", " ").title())
            title_label.setStyleSheet("font-weight: bold;")
            header_layout.addWidget(title_label)
            header_layout.addStretch()
            
            category_layout.addLayout(header_layout)
            
            # Content area (initially hidden)
            content_widget = QWidget()
            content_layout = QVBoxLayout(content_widget)
            content_widget.setVisible(False)
            
            # Get transformations for this category
            transformations = self.transformation_manager.get_transformations_for_category(category)
            
            # Create a checkbox for each transformation
            for transformation in transformations:
                checkbox = QCheckBox(transformation["title"])
                checkbox.setToolTip(transformation["description"])
                checkbox.stateChanged.connect(
                    lambda state, t=transformation: self.on_transformation_toggled(state, t)
                )
                content_layout.addWidget(checkbox)
                
                # Store the checkbox widget with its transformation data
                self.transformation_widgets[transformation["id"]] = {
                    "checkbox": checkbox,
                    "transformation": transformation
                }
            
            category_layout.addWidget(content_widget)
            
            # Connect toggle button
            toggle_button.clicked.connect(lambda checked, w=content_widget, b=toggle_button: 
                                         self.toggle_category(w, b))
            
            # Store reference to category frame
            self.category_frames[category] = {
                "frame": category_frame,
                "content": content_widget,
                "toggle": toggle_button
            }
            
            scroll_layout.addWidget(category_frame)
        
        scroll_area.setWidget(scroll_widget)
        bottom_layout.addWidget(scroll_area)
        
        # Add clear transformations button
        clear_button = QPushButton("Clear All Transformations")
        clear_button.clicked.connect(self.clear_transformations)
        bottom_layout.addWidget(clear_button)
        
        main_layout.addWidget(bottom_section)
        
        # Set central widget
        self.setCentralWidget(central_widget)
        
        # Create status bar
        self.statusBar().showMessage("Ready")
        
        # Create menu bar
        self.create_menu_bar()
    
    def toggle_category(self, content_widget, toggle_button):
        """Toggle visibility of category content."""
        is_visible = content_widget.isVisible()
        content_widget.setVisible(not is_visible)
        toggle_button.setText("-" if not is_visible else "+")
    
    def create_menu_bar(self):
        """Create the application menu bar."""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("File")
        
        new_action = QAction("New", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_note)
        file_menu.addAction(new_action)
        
        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_note)
        file_menu.addAction(save_action)
        
        save_desktop_action = QAction("Save to Desktop", self)
        save_desktop_action.setShortcut("Ctrl+D")
        save_desktop_action.triggered.connect(self.save_note_to_desktop)
        file_menu.addAction(save_desktop_action)
        
        load_action = QAction("Load", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.load_note)
        file_menu.addAction(load_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Settings menu
        settings_menu = menu_bar.addMenu("Settings")
        
        api_key_action = QAction("Set OpenAI API Key", self)
        api_key_action.triggered.connect(self.set_api_key)
        settings_menu.addAction(api_key_action)
        
        default_transformations_action = QAction("Set Default Transformations", self)
        default_transformations_action.triggered.connect(self.set_default_transformations)
        settings_menu.addAction(default_transformations_action)
        
        # Help menu
        help_menu = menu_bar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def load_audio_devices(self):
        """Load available audio input devices."""
        try:
            devices = sd.query_devices()
            input_devices = []
            
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    # Add device info including default sample rate
                    name = device['name']
                    if 'default_samplerate' in device:
                        sample_rate = int(device['default_samplerate'])
                        name += f" ({sample_rate} Hz)"
                    input_devices.append((i, name))
            
            self.device_combo.clear()
            for idx, name in input_devices:
                self.device_combo.addItem(name, idx)
            
            # Set the default device from config if available
            default_device = self.config.get("default_device")
            if default_device is not None:
                # Try to find by partial match since we added sample rate info
                for i in range(self.device_combo.count()):
                    if default_device in self.device_combo.itemText(i):
                        self.device_combo.setCurrentIndex(i)
                        break
            
            # If we have devices but none selected, select the first one
            if self.device_combo.count() > 0 and self.device_combo.currentIndex() < 0:
                self.device_combo.setCurrentIndex(0)
                
            # Show a warning if no input devices are found
            if self.device_combo.count() == 0:
                self.show_error("No audio input devices found. Please connect a microphone and restart the application.")
        except Exception as e:
            self.show_error(f"Error loading audio devices: {str(e)}")
    
    def start_recording(self):
        """Start recording audio from the selected device."""
        try:
            # Get selected device
            device_idx = self.device_combo.currentData()
            
            # Save the selected device as default (just the device name without sample rate)
            device_text = self.device_combo.currentText()
            # Extract just the device name without the sample rate
            device_name = device_text.split(" (")[0] if " (" in device_text else device_text
            self.config["default_device"] = device_name
            self.save_config()
            
            # Create and start recording thread
            self.recording_thread = RecordingThread(device_idx)
            self.recording_thread.finished.connect(self.on_recording_finished)
            self.recording_thread.error.connect(self.show_error)
            
            # Update UI
            self.record_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.statusBar().showMessage("Recording...")
            
            # Start recording
            self.recording_thread.start_recording()
            
            # Start a timer to show recording duration
            self.recording_start_time = time.time()
            self.recording_timer = QTimer(self)
            self.recording_timer.timeout.connect(self.update_recording_time)
            self.recording_timer.start(1000)  # Update every second
        except Exception as e:
            self.show_error(f"Error starting recording: {str(e)}")
    
    def update_recording_time(self):
        """Update the status bar with the current recording duration."""
        duration = int(time.time() - self.recording_start_time)
        minutes, seconds = divmod(duration, 60)
        self.statusBar().showMessage(f"Recording... {minutes:02d}:{seconds:02d}")
    
    def pause_recording(self):
        """Pause the current recording."""
        if self.recording_thread and hasattr(self.recording_thread, 'recording') and self.recording_thread.recording:
            self.recording_thread.pause_recording()
            self.statusBar().showMessage("Recording paused")
            self.record_button.setEnabled(True)
            self.pause_button.setEnabled(False)
    
    def stop_recording(self):
        """Stop the current recording."""
        if self.recording_thread and hasattr(self.recording_thread, 'recording') and self.recording_thread.recording:
            self.recording_timer.stop()
            self.recording_thread.stop_recording()
            self.statusBar().showMessage("Recording stopped")
    
    def on_recording_finished(self):
        """Handle the completion of the recording process."""
        # Update UI
        self.record_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        
        # Get the temporary audio file path
        self.temp_audio_file = self.recording_thread.temp_file_path
        
        # Enable transcription button
        self.transcribe_button.setEnabled(True)
        self.statusBar().showMessage("Recording saved. Click 'Transcribe' to process it.")
    
    def transcribe_audio(self):
        """Transcribe the recorded audio."""
        if not self.temp_audio_file or not os.path.exists(self.temp_audio_file):
            self.show_error("No recording available to transcribe")
            return
            
        # Start transcription
        self.statusBar().showMessage("Transcribing audio...")
        self.transcription_thread = TranscriptionThread(self.temp_audio_file)
        self.transcription_thread.finished.connect(self.on_transcription_finished)
        self.transcription_thread.error.connect(self.show_error)
        self.transcription_thread.progress.connect(self.statusBar().showMessage)
        
        # Start transcription in a new thread
        threading.Thread(target=self.transcription_thread.transcribe).start()
    
    def on_transcription_finished(self, text):
        """Handle the completion of the transcription process."""
        # Update UI with transcription
        self.raw_text.setText(text)
        
        # Enable clean button
        self.basic_cleanup_button.setEnabled(True)
        self.transform_cleanup_button.setEnabled(True)
        self.statusBar().showMessage("Transcription complete. Select transformations and click 'Clean Transcript' to process it.")
    
    def basic_cleanup(self):
        """Clean up the transcript using GPT with default transformations."""
        raw_text = self.raw_text.toPlainText()
        if not raw_text:
            self.show_error("No raw transcript to clean")
            return
            
        self.statusBar().showMessage("Cleaning up transcription with GPT...")
        
        # Get the system prompt based on default transformations
        system_prompt = self.transformation_manager.get_combined_prompt(
            self.transformation_manager.get_default_transformations()
        )
        
        # Start GPT cleanup
        self.cleanup_thread = CleanupThread(raw_text, system_prompt)
        self.cleanup_thread.finished.connect(self.on_cleanup_finished)
        self.cleanup_thread.error.connect(self.show_error)
        
        # Start cleanup in a new thread
        threading.Thread(target=self.cleanup_thread.cleanup).start()
    
    def cleanup_with_transformations(self):
        """Clean up the transcript using GPT with selected transformations."""
        raw_text = self.raw_text.toPlainText()
        if not raw_text:
            self.show_error("No raw transcript to clean")
            return
            
        self.statusBar().showMessage("Cleaning up transcription with GPT...")
        
        # Get the system prompt based on selected transformations
        system_prompt = self.transformation_manager.get_combined_prompt(self.selected_transformations)
        
        # Start GPT cleanup
        self.cleanup_thread = CleanupThread(raw_text, system_prompt)
        self.cleanup_thread.finished.connect(self.on_cleanup_finished)
        self.cleanup_thread.error.connect(self.show_error)
        
        # Start cleanup in a new thread
        threading.Thread(target=self.cleanup_thread.cleanup).start()
    
    def on_cleanup_finished(self, text):
        """Handle the completion of the GPT cleanup process."""
        # Update UI with cleaned text
        self.cleaned_text.setText(text)
        
        self.statusBar().showMessage("Ready")
        
        # Clean up temporary audio file
        if self.temp_audio_file and os.path.exists(self.temp_audio_file):
            try:
                os.remove(self.temp_audio_file)
                self.temp_audio_file = None
            except Exception as e:
                print(f"Error removing temporary file: {str(e)}")
    
    def new_note(self):
        """Clear both transcription text areas."""
        self.raw_text.clear()
        self.cleaned_text.clear()
        self.statusBar().showMessage("New note created")
    
    def save_note(self):
        """Save the content of the GPT-cleaned transcription to a file."""
        text = self.cleaned_text.toPlainText()
        if not text:
            self.show_error("Nothing to save")
            return
        
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Note", "", "Text Files (*.txt);;All Files (*)"
            )
            
            if file_path:
                with open(file_path, "w") as f:
                    f.write(text)
                self.statusBar().showMessage(f"Note saved to {file_path}")
        except Exception as e:
            self.show_error(f"Error saving note: {str(e)}")
    
    def save_note_to_desktop(self):
        """Save the content of the GPT-cleaned transcription to the desktop."""
        text = self.cleaned_text.toPlainText()
        if not text:
            self.show_error("Nothing to save")
            return
        
        try:
            # Get desktop path
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            
            # Generate a filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(desktop_path, f"voice_note_{timestamp}.txt")
            
            with open(file_path, "w") as f:
                f.write(text)
            self.statusBar().showMessage(f"Note saved to {file_path}")
        except Exception as e:
            self.show_error(f"Error saving note to desktop: {str(e)}")
    
    def load_note(self):
        """Load the content of a file into the GPT-cleaned transcription area."""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Load Note", "", "Text Files (*.txt);;All Files (*)"
            )
            
            if file_path:
                with open(file_path, "r") as f:
                    text = f.read()
                self.raw_text.clear()
                self.cleaned_text.setText(text)
                self.statusBar().showMessage(f"Note loaded from {file_path}")
        except Exception as e:
            self.show_error(f"Error loading note: {str(e)}")
    
    def copy_text_to_clipboard(self, text_area):
        """Copy the text from the given text area to the clipboard."""
        text = text_area.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.statusBar().showMessage("Copied to clipboard", 3000)
        else:
            self.statusBar().showMessage("Nothing to copy", 3000)
    
    def on_transformation_toggled(self, state, transformation):
        """Handle toggling of transformation checkboxes."""
        # If a transformation is being checked, uncheck the option checkboxes
        if state == Qt.Checked:
            self.selected_transformations.append(transformation)
        else:
            # Remove the transformation if it exists in the list
            self.selected_transformations = [t for t in self.selected_transformations 
                                           if t["id"] != transformation["id"]]
    
    def clear_transformations(self):
        """Clear all selected transformations."""
        for widget_data in self.transformation_widgets.values():
            widget_data["checkbox"].setChecked(False)
        self.selected_transformations = []
        self.statusBar().showMessage("All transformations cleared")
    
    def set_api_key(self):
        """Set the OpenAI API Key."""
        from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox
        
        current_key = self.config.get("api_key", "")
        api_key, ok = QInputDialog.getText(
            self, "OpenAI API Key", "Enter your OpenAI API Key:",
            QLineEdit.Password, current_key
        )
        
        if ok and api_key:
            # Validate the API key format (basic check)
            if not api_key.startswith("sk-") or len(api_key) < 20:
                QMessageBox.warning(
                    self, "Invalid API Key",
                    "The API key format appears to be invalid. OpenAI API keys typically start with 'sk-' and are longer."
                )
                return
                
            # Update the API key
            self.config["api_key"] = api_key
            openai.api_key = api_key
            self.save_config()
            
            # Show confirmation
            QMessageBox.information(
                self, "API Key Updated",
                "Your OpenAI API key has been updated successfully. You can now use the transcription and cleanup features."
            )
            self.statusBar().showMessage("API key updated successfully", 3000)
    
    def set_default_transformations(self):
        """Set the current transformations as default."""
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        
        # Ask for a name for the default set
        name, ok = QInputDialog.getText(
            self, "Default Transformations", "Enter a name for this default transformation set:",
            QLineEdit.Normal, "My Default Set"
        )
        
        if ok and name:
            # Save the current transformations as default
            self.config["default_transformations"] = {
                "name": name,
                "transformations": [t["id"] for t in self.selected_transformations]
            }
            self.save_config()
            self.statusBar().showMessage(f"Default transformations set: {name}")
    
    def apply_default_transformations(self):
        """Apply the default transformations if they exist."""
        default = self.config.get("default_transformations")
        if default:
            # Clear current selections
            self.clear_transformations()
            
            # Set transformations
            transformation_ids = default.get("transformations", [])
            for t_id in transformation_ids:
                if t_id in self.transformation_widgets:
                    self.transformation_widgets[t_id]["checkbox"].setChecked(True)
            
            self.statusBar().showMessage(f"Applied default transformations: {default.get('name', 'Default')}")
    
    def save_current_as_stack(self):
        """Save the current transformations as a named stack."""
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        
        # Ask for a name for the stack
        name, ok = QInputDialog.getText(
            self, "Save Transformation Stack", "Enter a name for this transformation stack:",
            QLineEdit.Normal, ""
        )
        
        if ok and name:
            # Save the current transformations as a stack
            stack_saved = self.transformation_manager.save_transformation_stack(
                name, self.selected_transformations
            )
            
            if stack_saved:
                # Save stacks to config
                self.save_transformation_stacks()
                # Update the stack combo
                self.update_stack_combo()
                self.statusBar().showMessage(f"Transformation stack saved: {name}")
    
    def apply_transformation_stack(self):
        """Apply the selected transformation stack."""
        stack_name = self.stack_combo.currentText()
        if not stack_name:
            return
            
        # Get the stack
        stack = self.transformation_manager.get_transformation_stack(stack_name)
        
        # Clear current selections
        self.clear_transformations()
        
        # Apply the stack
        for transformation in stack:
            t_id = transformation["id"]
            if t_id in self.transformation_widgets:
                self.transformation_widgets[t_id]["checkbox"].setChecked(True)
        
        self.statusBar().showMessage(f"Applied transformation stack: {stack_name}")
    
    def delete_transformation_stack(self):
        """Delete the selected transformation stack."""
        stack_name = self.stack_combo.currentText()
        if not stack_name:
            return
            
        # Confirm deletion
        from PySide6.QtWidgets import QMessageBox
        confirm = QMessageBox.question(
            self, "Delete Stack",
            f"Are you sure you want to delete the stack '{stack_name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            # Delete the stack
            deleted = self.transformation_manager.delete_transformation_stack(stack_name)
            
            if deleted:
                # Save stacks to config
                self.save_transformation_stacks()
                # Update the stack combo
                self.update_stack_combo()
                self.statusBar().showMessage(f"Transformation stack deleted: {stack_name}")
    
    def update_stack_combo(self):
        """Update the transformation stack combo box."""
        self.stack_combo.clear()
        stacks = self.transformation_manager.get_all_transformation_stacks()
        for name in stacks.keys():
            self.stack_combo.addItem(name)
    
    def save_transformation_stacks(self):
        """Save transformation stacks to config."""
        stacks = self.transformation_manager.get_all_transformation_stacks()
        
        # Convert transformations to IDs for storage
        serialized_stacks = {}
        for name, transformations in stacks.items():
            serialized_stacks[name] = [t["id"] for t in transformations]
        
        self.config["transformation_stacks"] = serialized_stacks
        self.save_config()
    
    def load_transformation_stacks(self):
        """Load transformation stacks from config."""
        serialized_stacks = self.config.get("transformation_stacks", {})
        
        # Convert IDs back to transformation objects
        for name, t_ids in serialized_stacks.items():
            transformations = []
            for t_id in t_ids:
                for category in self.transformation_manager.categories.values():
                    for t in category:
                        if t["id"] == t_id:
                            transformations.append(t)
                            break
            
            self.transformation_manager.save_transformation_stack(name, transformations)
        
        # Update the stack combo
        self.update_stack_combo()
    
    def show_about(self):
        """Show the about dialog."""
        QMessageBox.about(
            self, "About AI Voice Note Optimizer",
            f"{APP_NAME}\n\nA desktop application for recording audio, "
            "transcribing it with Whisper, cleaning it up with GPT, and managing notes with advanced transformation options."
        )
    
    def show_error(self, message):
        """Show an error message dialog."""
        QMessageBox.critical(self, "Error", message)
    
    def load_config(self):
        """Load configuration from file or create default."""
        self.config = {}
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    self.config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {str(e)}")
            # Create default config
            self.config = {
                "api_key": os.environ.get("OPENAI_API_KEY", ""),
                "default_device": None,
                "default_transformations": None,
                "transformation_stacks": {}
            }
    
    def save_config(self):
        """Save configuration to file."""
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f)
        except Exception as e:
            print(f"Error saving config: {str(e)}")
    
    def closeEvent(self, event):
        """Handle application close event."""
        # Save configuration
        self.save_config()
        
        # Clean up temporary audio file if it exists
        if self.temp_audio_file and os.path.exists(self.temp_audio_file):
            try:
                os.remove(self.temp_audio_file)
            except:
                pass
        
        event.accept()

def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    window = VoiceNotepadApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
