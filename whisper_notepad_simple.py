#!/usr/bin/env python3
"""
Whisper Notepad Simple

A simplified desktop application for recording audio, transcribing it with Whisper (via OpenAI API),
and optionally cleaning it up with GPT (via OpenAI API).

Dependencies:
- PySide6: Qt bindings for Python
- sounddevice: Audio recording
- soundfile: Audio file I/O
- openai: OpenAI API client
- numpy: Array manipulation (used with sounddevice)
"""

import sys
import os
import json
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
    QCheckBox, QSplitter, QFrame
)
from PySide6.QtCore import Qt, QSettings, QTimer, Signal, QObject, Slot
from PySide6.QtGui import QIcon, QFont, QAction, QClipboard, QPalette

# Constants
APP_NAME = "Whisper Notepad Simple"
CONFIG_FILE = os.path.expanduser("~/.whisper_notepad_simple_config.json")


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
    
    def _save_current_chunk(self):
        """Save the current chunk to a temporary file."""
        if not self.current_chunk:
            return
            
        try:
            # Create a temporary file for this chunk
            chunk_file = os.path.join(self.temp_dir, f"chunk_{len(self.chunk_files)}.wav")
            
            # Combine all frames in the current chunk
            chunk_data = np.concatenate(self.current_chunk, axis=0)
            
            # Save as WAV file
            sf.write(chunk_file, chunk_data, self.sample_rate)
            
            # Add to chunk files list
            self.chunk_files.append(chunk_file)
            
            # Clear the current chunk
            self.current_chunk = []
        except Exception as e:
            print(f"Error saving chunk: {e}")


class TranscriptionThread(QObject):
    """Thread for handling audio transcription to avoid UI freezing."""
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(str)
    
    def __init__(self, audio_file_path):
        super().__init__()
        self.audio_file_path = audio_file_path
        self.temp_dir = tempfile.mkdtemp()
        
    def transcribe(self):
        """Transcribe the audio file using OpenAI's Whisper API."""
        try:
            # Check if API key is set
            if not openai.api_key:
                self.error.emit("OpenAI API key is not set. Please set it in Settings > Set OpenAI API Key.")
                return
                
            # Check if file exists
            if not os.path.exists(self.audio_file_path):
                self.error.emit(f"Audio file not found: {self.audio_file_path}")
                return
                
            # Get file size
            file_size = os.path.getsize(self.audio_file_path) / (1024 * 1024)  # Size in MB
            
            # If file is larger than 23MB (leaving buffer), use chunking approach
            if file_size > 23:
                self.progress.emit(f"Large audio file detected ({file_size:.1f} MB). Processing in chunks...")
                text = self._transcribe_large_file()
            else:
                self.progress.emit("Transcribing audio...")
                
                # Compress audio to reduce file size if needed
                compressed_path = self._compress_audio(self.audio_file_path)
                
                # Open the audio file
                with open(compressed_path, "rb") as audio_file:
                    # Call Whisper API
                    response = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                
                # Extract text from response
                text = response.text
                
                # Clean up temporary compressed file if it's different from original
                if compressed_path != self.audio_file_path and os.path.exists(compressed_path):
                    try:
                        os.remove(compressed_path)
                    except:
                        pass
            
            # Return the transcribed text
            self.finished.emit(text)
            
            # Clean up temp directory
            self._cleanup_temp_files()
            
        except Exception as e:
            self.error.emit(f"Error during transcription: {str(e)}")
            self._cleanup_temp_files()
    
    def _compress_audio(self, audio_path, target_size_mb=15):
        """Compress audio file to reduce size while maintaining quality."""
        try:
            # Get file size
            file_size = os.path.getsize(audio_path) / (1024 * 1024)  # Size in MB
            
            # If file is already small enough, return original path
            if file_size <= target_size_mb:
                return audio_path
                
            self.progress.emit(f"Compressing audio to optimize for API limits...")
            
            # Load audio file
            data, sample_rate = sf.read(audio_path)
            
            # Create a temporary file for compressed audio
            fd, compressed_path = tempfile.mkstemp(suffix='.mp3', dir=self.temp_dir)
            os.close(fd)
            
            # Calculate target bitrate based on desired file size and duration
            duration = len(data) / sample_rate
            target_bitrate = int((target_size_mb * 8 * 1024) / duration)
            
            # Ensure bitrate is reasonable (between 32kbps and 128kbps)
            target_bitrate = max(32, min(128, target_bitrate))
            
            # Use ffmpeg to compress the audio (requires ffmpeg to be installed)
            import subprocess
            cmd = [
                'ffmpeg', '-y', '-i', audio_path, 
                '-b:a', f'{target_bitrate}k', 
                '-ac', '1',  # Convert to mono
                compressed_path
            ]
            
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Check if compression was successful
            if os.path.exists(compressed_path) and os.path.getsize(compressed_path) > 0:
                compressed_size = os.path.getsize(compressed_path) / (1024 * 1024)
                self.progress.emit(f"Compressed audio from {file_size:.1f}MB to {compressed_size:.1f}MB")
                return compressed_path
            else:
                # If compression failed, return original path
                return audio_path
                
        except Exception as e:
            self.progress.emit(f"Audio compression failed: {str(e)}. Using original file.")
            return audio_path
    
    def _transcribe_large_file(self):
        """Handle transcription of large audio files by splitting into chunks."""
        try:
            self.progress.emit("Splitting large audio file into chunks...")
            
            # Load audio file
            data, sample_rate = sf.read(self.audio_file_path)
            
            # Calculate chunk size (in samples) for approximately 5-minute chunks
            # This should result in files under 10MB each for typical audio quality
            chunk_duration = 5 * 60  # 5 minutes in seconds
            chunk_size = int(chunk_duration * sample_rate)
            
            # Calculate number of chunks
            total_samples = len(data)
            num_chunks = (total_samples + chunk_size - 1) // chunk_size  # Ceiling division
            
            # Create chunks and transcribe each one
            all_transcriptions = []
            
            for i in range(num_chunks):
                self.progress.emit(f"Processing chunk {i+1} of {num_chunks}...")
                
                # Extract chunk data
                start_idx = i * chunk_size
                end_idx = min(start_idx + chunk_size, total_samples)
                chunk_data = data[start_idx:end_idx]
                
                # Create a temporary file for this chunk
                fd, chunk_path = tempfile.mkstemp(suffix='.wav', dir=self.temp_dir)
                os.close(fd)
                
                # Save chunk to file
                sf.write(chunk_path, chunk_data, sample_rate)
                
                # Compress the chunk
                compressed_chunk_path = self._compress_audio(chunk_path)
                
                # Transcribe the chunk
                with open(compressed_chunk_path, "rb") as audio_file:
                    self.progress.emit(f"Transcribing chunk {i+1}...")
                    response = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                
                # Add to transcriptions
                all_transcriptions.append(response.text)
                
                # Clean up chunk files
                if os.path.exists(chunk_path):
                    try:
                        os.remove(chunk_path)
                    except:
                        pass
                
                if compressed_chunk_path != chunk_path and os.path.exists(compressed_chunk_path):
                    try:
                        os.remove(compressed_chunk_path)
                    except:
                        pass
            
            # Combine all transcriptions
            combined_text = " ".join(all_transcriptions)
            
            return combined_text
            
        except Exception as e:
            self.error.emit(f"Error processing large audio file: {str(e)}")
            return ""
    
    def _cleanup_temp_files(self):
        """Clean up temporary files and directory."""
        try:
            # Remove the temporary directory and all its contents
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            print(f"Error cleaning up temporary files: {e}")


class CleanupThread(QObject):
    """Thread for handling text cleanup with GPT to avoid UI freezing."""
    finished = Signal(str)
    error = Signal(str)
    
    def __init__(self, text):
        super().__init__()
        self.text = text
        
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
            
            # Enhanced system prompt for text cleanup
            system_prompt = """You are a transcription processing assistant. Your task is to transform raw dictation into a readable and presentable format by:

1. Adjusting spacing and paragraph structure for better readability
2. Fixing grammar, spelling, and punctuation errors
3. Ensuring proper capitalization and sentence structure
4. Removing filler words, verbal tics, and repetitions
5. Maintaining the original meaning and all crucial information
6. Organizing ideas into logical paragraphs
7. Making light edits for clarity where appropriate

The text is from a voice recording that was transcribed automatically. Focus on improving readability while preserving all meaningful content. Do not add new information or change the meaning of the original text."""
            
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
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


class WhisperNotepadApp(QMainWindow):
    """Main application window for Whisper Notepad Simple."""
    
    def __init__(self):
        super().__init__()
        self.recording_thread = None
        self.transcription_thread = None
        self.cleanup_thread = None
        self.temp_audio_file = None
        
        # Load configuration
        self.load_config()
        
        # Initialize OpenAI API
        openai.api_key = self.config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
        
        # Set up the UI
        self.init_ui()
        
        # Load available audio devices
        self.load_audio_devices()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 700)
        
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
        
        # Add save default device button
        device_button_layout = QHBoxLayout()
        self.save_default_device_button = QPushButton("Set as Default")
        self.save_default_device_button.setToolTip("Save selected device as default")
        self.save_default_device_button.clicked.connect(self.save_default_device)
        device_button_layout.addWidget(self.device_combo)
        device_button_layout.addWidget(self.save_default_device_button)
        
        device_layout.addLayout(device_button_layout)
        top_layout.addWidget(device_group)
        
        # Recording controls
        recording_group = QGroupBox("Recording")
        recording_layout = QHBoxLayout(recording_group)
        
        # Record button with icon
        self.record_button = QPushButton("⏺")
        self.record_button.setToolTip("Start Recording")
        self.record_button.clicked.connect(self.start_recording)
        self.record_button.setFixedWidth(40)
        
        # Pause button with icon
        self.pause_button = QPushButton("⏸")
        self.pause_button.setToolTip("Pause Recording")
        self.pause_button.clicked.connect(self.pause_recording)
        self.pause_button.setEnabled(False)
        self.pause_button.setFixedWidth(40)
        
        # Stop button with icon
        self.stop_button = QPushButton("⏹")
        self.stop_button.setToolTip("Stop Recording")
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.setEnabled(False)
        self.stop_button.setFixedWidth(40)
        
        # Clear recording button
        self.clear_recording_button = QPushButton("🗑")
        self.clear_recording_button.setToolTip("Clear Recording")
        self.clear_recording_button.clicked.connect(self.clear_recording)
        self.clear_recording_button.setEnabled(False)
        self.clear_recording_button.setFixedWidth(40)
        
        recording_layout.addWidget(self.record_button)
        recording_layout.addWidget(self.pause_button)
        recording_layout.addWidget(self.stop_button)
        recording_layout.addWidget(self.clear_recording_button)
        top_layout.addWidget(recording_group)
        
        # Process controls
        process_group = QGroupBox("Processing")
        process_layout = QVBoxLayout(process_group)
        
        # Add checkbox for text cleanup
        self.cleanup_checkbox = QCheckBox("Process Transcription")
        self.cleanup_checkbox.setChecked(True)
        self.cleanup_checkbox.setToolTip("Apply AI-powered text processing to improve readability")
        process_layout.addWidget(self.cleanup_checkbox)
        
        # Transcribe button
        button_layout = QHBoxLayout()
        self.transcribe_button = QPushButton("Transcribe")
        self.transcribe_button.setToolTip("Transcribe the recorded audio")
        self.transcribe_button.clicked.connect(self.transcribe_audio)
        self.transcribe_button.setEnabled(False)
        
        # Clear button
        self.clear_button = QPushButton("Clear All")
        self.clear_button.setToolTip("Clear all transcripts")
        self.clear_button.clicked.connect(self.new_note)
        
        button_layout.addWidget(self.transcribe_button)
        button_layout.addWidget(self.clear_button)
        process_layout.addLayout(button_layout)
        
        top_layout.addWidget(process_group)
        
        main_layout.addWidget(top_section)
        
        # Create middle section with transcription areas
        middle_section = QSplitter(Qt.Vertical)
        
        # Raw transcription area
        raw_group = QGroupBox("Raw Transcription")
        raw_layout = QVBoxLayout(raw_group)
        
        # Add copy button for raw text
        raw_top_layout = QHBoxLayout()
        self.raw_copy_button = QPushButton("Copy")
        self.raw_copy_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.raw_copy_button.setToolTip("Copy to Clipboard")
        self.raw_copy_button.clicked.connect(lambda: self.copy_text_to_clipboard(self.raw_text))
        raw_top_layout.addStretch()
        raw_top_layout.addWidget(self.raw_copy_button)
        raw_layout.addLayout(raw_top_layout)
        
        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        
        # Set raw text to be lighter and smaller
        raw_font = self.raw_text.font()
        raw_font.setPointSize(raw_font.pointSize() - 1)
        self.raw_text.setFont(raw_font)
        
        # Set text color to light gray
        raw_palette = self.raw_text.palette()
        raw_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.gray)
        self.raw_text.setPalette(raw_palette)
        
        raw_layout.addWidget(self.raw_text)
        middle_section.addWidget(raw_group)
        
        # Cleaned transcription area
        cleaned_group = QGroupBox("Clean Transcription")
        cleaned_layout = QVBoxLayout(cleaned_group)
        
        # Add copy button for cleaned text
        cleaned_top_layout = QHBoxLayout()
        self.copy_button = QPushButton("Copy")
        self.copy_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_button.setToolTip("Copy to Clipboard")
        self.copy_button.clicked.connect(lambda: self.copy_text_to_clipboard(self.cleaned_text))
        
        # Add save button
        self.save_button = QPushButton("Save")
        self.save_button.setIcon(QIcon.fromTheme("document-save"))
        self.save_button.setToolTip("Save to File")
        self.save_button.clicked.connect(self.save_note)
        
        cleaned_top_layout.addStretch()
        cleaned_top_layout.addWidget(self.copy_button)
        cleaned_top_layout.addWidget(self.save_button)
        cleaned_layout.addLayout(cleaned_top_layout)
        
        self.cleaned_text = QTextEdit()
        cleaned_layout.addWidget(self.cleaned_text)
        
        middle_section.addWidget(cleaned_group)
        
        main_layout.addWidget(middle_section, 1)  # Give it a stretch factor of 1
        
        # Set central widget
        self.setCentralWidget(central_widget)
        
        # Create status bar
        self.statusBar().showMessage("Ready")
        
        # Create menu bar
        self.create_menu_bar()
    
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
            default_device_id = self.config.get("default_device_id")
            default_device_name = self.config.get("default_device")
            
            # First try to set by device ID (more reliable)
            if default_device_id is not None:
                for i in range(self.device_combo.count()):
                    if self.device_combo.itemData(i) == default_device_id:
                        self.device_combo.setCurrentIndex(i)
                        break
            # If that fails, try by name
            elif default_device_name is not None:
                # Try to find by partial match since we added sample rate info
                for i in range(self.device_combo.count()):
                    if default_device_name in self.device_combo.itemText(i):
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
    
    def save_default_device(self):
        """Save the currently selected device as the default."""
        if self.device_combo.currentIndex() >= 0:
            device_idx = self.device_combo.currentData()
            device_text = self.device_combo.currentText()
            # Extract just the device name without the sample rate
            device_name = device_text.split(" (")[0] if " (" in device_text else device_text
            
            self.config["default_device"] = device_name
            self.config["default_device_id"] = device_idx
            self.save_config()
            self.statusBar().showMessage(f"Device '{device_name}' set as default", 3000)
    
    def clear_recording(self):
        """Clear the current recording."""
        self.temp_audio_file = None
        self.transcribe_button.setEnabled(False)
        self.clear_recording_button.setEnabled(False)
        self.statusBar().showMessage("Recording cleared", 3000)
    
    def start_recording(self):
        """Start recording audio from the selected device."""
        try:
            # Get selected device
            device_idx = self.device_combo.currentData()
            
            # Create and start recording thread
            self.recording_thread = RecordingThread(device_idx)
            self.recording_thread.finished.connect(self.on_recording_finished)
            self.recording_thread.error.connect(self.show_error)
            
            # Update UI
            self.record_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.clear_recording_button.setEnabled(False)
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
            if self.recording_thread.paused:
                # Resume recording
                self.recording_thread.resume_recording()
                self.pause_button.setText("Pause")
                self.statusBar().showMessage("Recording resumed")
            else:
                # Pause recording
                self.recording_thread.pause_recording()
                self.pause_button.setText("Resume")
                self.statusBar().showMessage("Recording paused")
    
    def stop_recording(self):
        """Stop the current recording."""
        if self.recording_thread and hasattr(self.recording_thread, 'recording') and self.recording_thread.recording:
            self.recording_timer.stop()
            self.recording_thread.stop_recording()
            self.statusBar().showMessage("Recording stopped")
    
    def on_recording_finished(self):
        """Handle the completion of the recording process."""
        try:
            # Get the temporary file path from the recording thread
            if hasattr(self.recording_thread, 'temp_file_path'):
                self.temp_audio_file = self.recording_thread.temp_file_path
                
                # Update UI
                self.record_button.setEnabled(True)
                self.pause_button.setEnabled(False)
                self.stop_button.setEnabled(False)
                self.transcribe_button.setEnabled(True)
                self.clear_recording_button.setEnabled(True)
                
                # Stop and clear the timer
                if hasattr(self, 'recording_timer'):
                    self.recording_timer.stop()
                
                self.statusBar().showMessage("Recording finished. Ready to transcribe.")
            else:
                self.record_button.setEnabled(True)
                self.pause_button.setEnabled(False)
                self.stop_button.setEnabled(False)
                self.statusBar().showMessage("Recording failed or was too short.")
                
            # Clean up
            self.recording_thread = None
        except Exception as e:
            self.show_error(f"Error finalizing recording: {str(e)}")
    
    def transcribe_audio(self):
        """Transcribe the recorded audio."""
        if not self.temp_audio_file:
            self.show_error("No recording to transcribe.")
            return
            
        try:
            # Check if API key is set
            if not openai.api_key:
                self.show_error("OpenAI API key is not set. Please set it in Settings > Set OpenAI API Key.")
                return
                
            # Update UI
            self.transcribe_button.setText("Transcribing...")
            self.transcribe_button.setEnabled(False)
            self.statusBar().showMessage("Transcribing audio...")
            
            # Create and start transcription thread
            self.transcription_thread = TranscriptionThread(self.temp_audio_file)
            self.transcription_thread.finished.connect(self.on_transcription_finished)
            self.transcription_thread.error.connect(self.show_error)
            self.transcription_thread.progress.connect(lambda msg: self.statusBar().showMessage(msg))
            
            # Start transcription in a separate thread
            threading.Thread(target=self.transcription_thread.transcribe).start()
        except Exception as e:
            self.transcribe_button.setText("Transcribe")
            self.transcribe_button.setEnabled(True)
            self.show_error(f"Error starting transcription: {str(e)}")
            
    def on_transcription_finished(self, text):
        """Handle the completion of the transcription process."""
        try:
            # Reset transcribe button
            self.transcribe_button.setText("Transcribe")
            self.transcribe_button.setEnabled(True)
            
            # Display the raw transcription
            self.raw_text.setText(text)
            
            # If cleanup is enabled, process the text
            if self.cleanup_checkbox.isChecked():
                self.statusBar().showMessage("Processing transcription...")
                self.cleanup_text(text)
            else:
                # Otherwise, just copy the raw text to the cleaned area
                self.cleaned_text.setText(text)
                self.statusBar().showMessage("Transcription complete.")
        except Exception as e:
            self.show_error(f"Error processing transcription: {str(e)}")
    
    def cleanup_text(self, text):
        """Clean up the transcript using GPT."""
        if not text:
            self.show_error("No text to clean up")
            return
            
        self.statusBar().showMessage("Cleaning up transcription with GPT...")
        
        # Start GPT cleanup
        self.cleanup_thread = CleanupThread(text)
        self.cleanup_thread.finished.connect(self.on_cleanup_finished)
        self.cleanup_thread.error.connect(self.show_error)
        
        # Start cleanup in a new thread
        threading.Thread(target=self.cleanup_thread.cleanup).start()
    
    def on_cleanup_finished(self, text):
        """Handle the completion of the GPT cleanup process."""
        # Update UI with cleaned text
        self.cleaned_text.setText(text)
        
        self.statusBar().showMessage("Transcription and cleanup complete.")
        
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
        """Save the content of the cleaned transcription to a file."""
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
        """Save the content of the cleaned transcription to the desktop."""
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
        """Load the content of a file into the cleaned transcription area."""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Load Note", "", "Text Files (*.txt);;All Files (*)"
            )
            
            if file_path:
                with open(file_path, "r") as f:
                    text = f.read()
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
    
    def set_api_key(self):
        """Set the OpenAI API Key."""
        from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox
        
        current_key = self.config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
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
    
    def show_about(self):
        """Show the about dialog."""
        QMessageBox.about(
            self, "About " + APP_NAME,
            f"<h1>{APP_NAME}</h1>"
            "<p>A simple desktop application for recording audio, transcribing it with Whisper API, "
            "and optionally cleaning it up with GPT.</p>"
            "<p>Created by Daniel Rosehill</p>"
        )
    
    def show_error(self, message):
        """Show an error message dialog."""
        QMessageBox.critical(self, "Error", message)
    
    def load_config(self):
        """Load configuration from file or create default."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    self.config = json.load(f)
            else:
                self.config = {
                    "api_key": os.environ.get("OPENAI_API_KEY", ""),
                    "default_device": None,
                    "default_device_id": None
                }
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = {
                "api_key": os.environ.get("OPENAI_API_KEY", ""),
                "default_device": None,
                "default_device_id": None
            }
    
    def save_config(self):
        """Save configuration to file."""
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def closeEvent(self, event):
        """Handle application close event."""
        # Save config
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
    window = WhisperNotepadApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
