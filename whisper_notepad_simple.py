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
    QCheckBox, QSplitter, QFrame, QToolButton, QProgressBar, QStyle
)
from PySide6.QtCore import Qt, QSettings, QTimer, Signal, QObject, Slot
from PySide6.QtGui import QIcon, QFont, QAction, QClipboard, QPalette, QColor, QKeySequence, QShortcut, QPainter, QPixmap

# Constants
APP_NAME = "Whisper Notepad Simple"
CONFIG_FILE = os.path.expanduser("~/.whisper_notepad_simple_config.json")

# Text transformation styles
TEXT_TRANSFORMATIONS = {
    "Standard": "You are a text formatting assistant. Your ONLY task is to take the raw text provided by the user and reformat it for clarity and readability. Specifically:\n\n1. Adjust spacing and paragraph structure for better readability\n2. Fix grammar, spelling, and punctuation errors\n3. Ensure proper capitalization and sentence structure\n4. Remove filler words, verbal tics, and repetitions\n5. Maintain the original meaning and all crucial information\n6. Organize ideas into logical paragraphs with appropriate headers where needed\n7. Make light edits for clarity where appropriate\n\nIMPORTANT: Do NOT respond as if you are an AI assistant. Do NOT add any commentary, explanations, or responses to the text. Simply return the reformatted version of the exact text provided. The output should ONLY be the reformatted text, nothing else.",
    
    "Email Format": "You are a text formatting assistant. Your ONLY task is to take the raw text provided by the user and reformat it into a professional email format. Specifically:\n\n1. Create a proper email structure with greeting and sign-off\n2. Organize content into clear paragraphs\n3. Fix grammar, spelling, and punctuation errors\n4. Remove filler words and verbal tics\n5. Maintain a professional tone throughout\n6. Keep the original meaning and all crucial information\n7. Add appropriate subject line if context allows\n\nIMPORTANT: Do NOT respond as if you are an AI assistant. Do NOT add any commentary, explanations, or responses to the text. Simply return the reformatted version as a professional email. The output should ONLY be the reformatted email text, nothing else.",
    
    "Voice Prompt": "You are a text formatting assistant. Your ONLY task is to take the raw text provided by the user and reformat it into a clear, concise voice prompt suitable for AI voice assistants. Specifically:\n\n1. Make the text direct, clear, and conversational\n2. Remove unnecessary words and phrases\n3. Fix grammar and structure for natural speech patterns\n4. Format as a direct instruction or query\n5. Maintain the original intent and all crucial information\n6. Optimize for voice recognition systems\n\nIMPORTANT: Do NOT respond as if you are an AI assistant. Do NOT add any commentary, explanations, or responses to the text. Simply return the reformatted version as a voice prompt. The output should ONLY be the reformatted voice prompt, nothing else.",
    
    "System Prompt": "You are a text formatting assistant. Your ONLY task is to take the raw text provided by the user and reformat it into a well-structured system prompt for AI systems. Specifically:\n\n1. Format as clear instructions for an AI system\n2. Organize into logical sections with appropriate structure\n3. Use clear, unambiguous language\n4. Include specific guidelines and constraints\n5. Define the AI's role and boundaries\n6. Maintain all crucial information from the original text\n7. Format with appropriate markdown or structure if needed\n\nIMPORTANT: Do NOT respond as if you are an AI assistant. Do NOT add any commentary, explanations, or responses to the text. Simply return the reformatted version as a system prompt. The output should ONLY be the reformatted system prompt, nothing else.",
    
    "Personal Email": "You are a text formatting assistant. Your ONLY task is to take the raw text provided by the user and reformat it into a friendly, personal email. Specifically:\n\n1. Create a warm, conversational tone\n2. Include appropriate casual greeting and sign-off\n3. Organize content into natural-sounding paragraphs\n4. Fix grammar, spelling, and punctuation errors\n5. Remove filler words and verbal tics\n6. Maintain the original meaning and all crucial information\n\nIMPORTANT: Do NOT respond as if you are an AI assistant. Do NOT add any commentary, explanations, or responses to the text. Simply return the reformatted version as a personal email. The output should ONLY be the reformatted email text, nothing else.",
    
    "Technical Documentation": "You are a text formatting assistant. Your ONLY task is to take the raw text provided by the user and reformat it into clear technical documentation. Specifically:\n\n1. Use proper technical writing style and structure\n2. Organize with appropriate headings and subheadings\n3. Use precise, unambiguous language\n4. Format code snippets, parameters, or technical terms appropriately\n5. Fix grammar, spelling, and punctuation errors\n6. Create logical flow with appropriate transitions\n7. Maintain all technical details and crucial information\n\nIMPORTANT: Do NOT respond as if you are an AI assistant. Do NOT add any commentary, explanations, or responses to the text. Simply return the reformatted version as technical documentation. The output should ONLY be the reformatted technical documentation, nothing else.",
    
    "Shakespearean Style": "You are a text formatting assistant. Your ONLY task is to take the raw text provided by the user and reformat it in the style of William Shakespeare. Specifically:\n\n1. Use Early Modern English vocabulary and grammar\n2. Incorporate Shakespearean phrases, metaphors, and expressions\n3. Structure with appropriate rhythm and flow\n4. Maintain the original meaning and all crucial information\n5. Use poetic devices where appropriate\n6. Include Shakespearean-style greetings and closings if relevant\n\nIMPORTANT: Do NOT respond as if you are an AI assistant. Do NOT add any commentary, explanations, or responses to the text. Simply return the reformatted version in Shakespearean style. The output should ONLY be the reformatted text, nothing else."
}

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
    
    def __init__(self, text, transformation_style="Standard"):
        super().__init__()
        self.text = text
        self.transformation_style = transformation_style
        
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
            
            # Get the appropriate system prompt based on transformation style
            system_prompt = TEXT_TRANSFORMATIONS.get(self.transformation_style, TEXT_TRANSFORMATIONS["Standard"])
            
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
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
        self.recording_timer = None
        self.recording_time = 0
        self.is_recording = False
        self.is_paused = False
        
        # Load configuration
        self.load_config()
        
        # Set OpenAI API key if available
        if "api_key" in self.config and self.config["api_key"]:
            openai.api_key = self.config["api_key"]
        
        # Initialize UI
        self.init_ui()
        
        # Load audio devices
        self.load_audio_devices()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 700)
        
        # Set application style
        self.setup_style()
        
        # Create central widget and main layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Create top section with audio controls
        top_section = QWidget()
        top_layout = QHBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        
        # Audio device selection
        device_group = QGroupBox("Audio Device")
        device_layout = QVBoxLayout(device_group)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(30)
        
        # Add save default device button
        device_button_layout = QHBoxLayout()
        self.save_default_device_button = QPushButton("Set as Default")
        self.save_default_device_button.setToolTip("Save selected device as default (Ctrl+D)")
        self.save_default_device_button.setMinimumHeight(30)
        self.save_default_device_button.clicked.connect(self.save_default_device)
        device_button_layout.addWidget(self.device_combo)
        device_button_layout.addWidget(self.save_default_device_button)
        
        device_layout.addLayout(device_button_layout)
        top_layout.addWidget(device_group)
        
        # Recording controls
        recording_group = QGroupBox("Recording")
        recording_layout = QVBoxLayout(recording_group)
        
        # Add recording time display
        self.time_display = QLabel("00:00")
        self.time_display.setAlignment(Qt.AlignCenter)
        self.time_display.setStyleSheet("font-size: 16px; font-weight: bold;")
        recording_layout.addWidget(self.time_display)
        
        # Button layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(5)
        
        # Record button with custom icon
        self.record_button = QPushButton()
        self.record_button.setToolTip("Start Recording (F5)")
        self.record_button.clicked.connect(self.start_recording)
        self.record_button.setMinimumSize(40, 40)
        
        # Create a custom recording icon (red circle)
        record_pixmap = QPixmap(16, 16)
        record_pixmap.fill(Qt.transparent)
        painter = QPainter(record_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(255, 0, 0))  # Red color
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        self.record_button.setIcon(QIcon(record_pixmap))
        
        # Pause button with icon
        self.pause_button = QPushButton()
        self.pause_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        self.pause_button.setToolTip("Pause Recording (F6)")
        self.pause_button.clicked.connect(self.pause_recording)
        self.pause_button.setEnabled(False)
        self.pause_button.setMinimumSize(40, 40)
        
        # Stop button with icon
        self.stop_button = QPushButton()
        self.stop_button.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_button.setToolTip("Stop Recording (F7)")
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumSize(40, 40)
        
        # Stop & Transcribe button with icon
        self.stop_and_transcribe_button = QPushButton()
        self.stop_and_transcribe_button.setIcon(self.style().standardIcon(QStyle.SP_MediaSkipForward))
        self.stop_and_transcribe_button.setToolTip("Stop Recording & Transcribe (F8)")
        self.stop_and_transcribe_button.clicked.connect(self.stop_and_transcribe)
        self.stop_and_transcribe_button.setEnabled(False)
        self.stop_and_transcribe_button.setMinimumSize(40, 40)
        
        # Clear recording button
        self.clear_recording_button = QPushButton()
        self.clear_recording_button.setIcon(self.style().standardIcon(QStyle.SP_DialogDiscardButton))
        self.clear_recording_button.setToolTip("Clear Recording (Ctrl+Shift+C)")
        self.clear_recording_button.clicked.connect(self.clear_recording)
        self.clear_recording_button.setEnabled(False)
        self.clear_recording_button.setMinimumSize(40, 40)
        
        buttons_layout.addWidget(self.record_button)
        buttons_layout.addWidget(self.pause_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addWidget(self.stop_and_transcribe_button)
        buttons_layout.addWidget(self.clear_recording_button)
        recording_layout.addLayout(buttons_layout)
        
        top_layout.addWidget(recording_group)
        
        # Process controls
        process_group = QGroupBox("Processing")
        process_layout = QVBoxLayout(process_group)
        
        # Add checkbox for text cleanup
        self.cleanup_checkbox = QCheckBox("Process Transcription with GPT")
        self.cleanup_checkbox.setChecked(True)
        self.cleanup_checkbox.setToolTip("Apply AI-powered text processing to improve readability")
        process_layout.addWidget(self.cleanup_checkbox)
        
        # Add transformation style selector
        transformation_layout = QHBoxLayout()
        transformation_label = QLabel("Transformation Style:")
        self.transformation_combo = QComboBox()
        for style in TEXT_TRANSFORMATIONS.keys():
            self.transformation_combo.addItem(style)
        
        # Set default transformation style from config
        default_style = self.config.get("default_transformation", "Standard")
        if default_style in TEXT_TRANSFORMATIONS:
            self.transformation_combo.setCurrentText(default_style)
            
        self.transformation_combo.setToolTip("Select the style of text transformation to apply")
        self.transformation_combo.setEnabled(True)
        transformation_layout.addWidget(transformation_label)
        transformation_layout.addWidget(self.transformation_combo)
        process_layout.addLayout(transformation_layout)
        
        # Connect cleanup checkbox to enable/disable transformation combo
        self.cleanup_checkbox.toggled.connect(self.transformation_combo.setEnabled)
        
        # Add checkbox for auto-transcribe
        self.auto_transcribe_checkbox = QCheckBox("Auto-Transcribe After Recording")
        self.auto_transcribe_checkbox.setChecked(False)
        self.auto_transcribe_checkbox.setToolTip("Automatically transcribe audio after stopping recording")
        process_layout.addWidget(self.auto_transcribe_checkbox)
        
        # Transcribe button
        button_layout = QHBoxLayout()
        self.transcribe_button = QPushButton("Transcribe")
        self.transcribe_button.setToolTip("Transcribe the recorded audio (Ctrl+T)")
        self.transcribe_button.clicked.connect(self.transcribe_audio)
        self.transcribe_button.setEnabled(False)
        self.transcribe_button.setMinimumHeight(40)
        
        # Clear button
        self.clear_button = QPushButton("Clear All")
        self.clear_button.setToolTip("Clear all transcripts (Ctrl+N)")
        self.clear_button.clicked.connect(self.new_note)
        self.clear_button.setMinimumHeight(40)
        
        button_layout.addWidget(self.transcribe_button)
        button_layout.addWidget(self.clear_button)
        process_layout.addLayout(button_layout)
        
        top_layout.addWidget(process_group)
        
        main_layout.addWidget(top_section)
        
        # Create middle section with transcription areas
        middle_section = QSplitter(Qt.Vertical)
        middle_section.setHandleWidth(8)
        middle_section.setChildrenCollapsible(False)
        
        # Raw transcription area
        raw_group = QGroupBox("Raw Transcription")
        raw_layout = QVBoxLayout(raw_group)
        
        # Add copy button for raw text
        raw_top_layout = QHBoxLayout()
        self.raw_copy_button = QPushButton("Copy")
        self.raw_copy_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.raw_copy_button.setToolTip("Copy to Clipboard (Ctrl+Shift+R)")
        self.raw_copy_button.clicked.connect(lambda: self.copy_text_to_clipboard(self.raw_text))
        raw_top_layout.addStretch()
        raw_top_layout.addWidget(self.raw_copy_button)
        raw_layout.addLayout(raw_top_layout)
        
        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        
        # Set raw text to be lighter and smaller
        raw_font = self.raw_text.font()
        raw_font.setPointSize(raw_font.pointSize() - 1)
        self.raw_text.setFont(raw_font)
        raw_layout.addWidget(self.raw_text)
        
        middle_section.addWidget(raw_group)
        
        # Clean transcription area
        clean_group = QGroupBox("Clean Transcription")
        clean_layout = QVBoxLayout(clean_group)
        
        # Add buttons for clean text
        clean_top_layout = QHBoxLayout()
        
        self.clean_copy_button = QPushButton("Copy")
        self.clean_copy_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.clean_copy_button.setToolTip("Copy to Clipboard (Ctrl+Shift+C)")
        self.clean_copy_button.clicked.connect(lambda: self.copy_text_to_clipboard(self.cleaned_text))
        
        self.save_button = QPushButton("Save")
        self.save_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.save_button.setToolTip("Save to File (Ctrl+S)")
        self.save_button.clicked.connect(self.save_note)
        
        self.load_button = QPushButton("Load")
        self.load_button.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.load_button.setToolTip("Load from File (Ctrl+O)")
        self.load_button.clicked.connect(self.load_note)
        
        clean_top_layout.addStretch()
        clean_top_layout.addWidget(self.clean_copy_button)
        clean_top_layout.addWidget(self.save_button)
        clean_top_layout.addWidget(self.load_button)
        clean_layout.addLayout(clean_top_layout)
        
        self.cleaned_text = QTextEdit()
        self.cleaned_text.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)
        clean_layout.addWidget(self.cleaned_text)
        
        middle_section.addWidget(clean_group)
        
        # Set initial sizes for the splitter
        middle_section.setSizes([300, 400])
        
        main_layout.addWidget(middle_section, 1)
        
        # Status bar
        self.statusBar().showMessage("Ready")
        
        # Set central widget
        self.setCentralWidget(central_widget)
        
        # Create menu bar
        self.create_menu_bar()
        
        # Setup keyboard shortcuts
        self.setup_shortcuts()
        
        # Setup recording timer
        self.recording_timer = QTimer()
        self.recording_timer.timeout.connect(self.update_recording_time)
        
    def setup_style(self):
        """Set up the application style."""
        # Set application-wide stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
                background-color: #ffffff;
            }
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border: 1px solid #bbbbbb;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
            QPushButton:disabled {
                background-color: #f8f8f8;
                color: #aaaaaa;
                border: 1px solid #dddddd;
            }
            QComboBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 1px 18px 1px 3px;
                min-width: 6em;
                background-color: #ffffff;
            }
            QComboBox:hover {
                border: 1px solid #bbbbbb;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 15px;
                border-left-width: 1px;
                border-left-color: #cccccc;
                border-left-style: solid;
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }
            QSplitter::handle {
                background-color: #cccccc;
            }
            QSplitter::handle:horizontal {
                width: 4px;
            }
            QSplitter::handle:vertical {
                height: 4px;
            }
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        
    def setup_shortcuts(self):
        """Set up keyboard shortcuts for the application."""
        # File menu shortcuts
        QShortcut(QKeySequence("Ctrl+N"), self, self.new_note)
        QShortcut(QKeySequence("Ctrl+O"), self, self.load_note)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_note)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
        
        # Recording shortcuts
        QShortcut(QKeySequence("F5"), self, self.start_recording)
        QShortcut(QKeySequence("F6"), self, self.pause_recording)
        QShortcut(QKeySequence("F7"), self, self.stop_recording)
        QShortcut(QKeySequence("F8"), self, self.stop_and_transcribe)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self.clear_recording)
        
        # Transcription shortcuts
        QShortcut(QKeySequence("Ctrl+T"), self, self.transcribe_audio)
        
        # Copy shortcuts
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, lambda: self.copy_text_to_clipboard(self.raw_text))
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, lambda: self.copy_text_to_clipboard(self.cleaned_text))
        
        # Device shortcut
        QShortcut(QKeySequence("Ctrl+D"), self, self.save_default_device)
    
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
        save_desktop_action.setShortcut("Ctrl+Shift+D")  # Changed from Ctrl+D to avoid conflict with device shortcut
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
        
    def update_recording_time(self):
        """Update the recording time display."""
        self.recording_time += 1
        minutes = self.recording_time // 60
        seconds = self.recording_time % 60
        self.time_display.setText(f"{minutes:02d}:{seconds:02d}")
        
    def start_recording(self):
        """Start recording audio from the selected device."""
        if not self.recording_thread:
            try:
                # Get selected device
                device_id = self.device_combo.currentData()
                
                if device_id is None:
                    self.show_error("No audio device selected")
                    return
                
                # Create recording thread
                self.recording_thread = RecordingThread(device_id)
                
                # Connect signals
                self.recording_thread.error.connect(self.show_error)
                self.recording_thread.finished.connect(self.on_recording_finished)
                
                # Start recording
                self.recording_thread.start_recording()
                
                # Update UI
                self.record_button.setEnabled(False)
                self.pause_button.setEnabled(True)
                self.stop_button.setEnabled(True)
                self.stop_and_transcribe_button.setEnabled(True)
                self.clear_recording_button.setEnabled(False)
                self.transcribe_button.setEnabled(False)
                self.device_combo.setEnabled(False)
                self.save_default_device_button.setEnabled(False)
                
                # Set recording flag
                self.is_recording = True
                self.is_paused = False
                
                # Start timer
                self.recording_time = 0
                self.recording_timer.start(1000)  # Update every second
                
                # Update status
                self.statusBar().showMessage("Recording...")
            except Exception as e:
                self.show_error(f"Error starting recording: {str(e)}")
                self.recording_thread = None
                
    def pause_recording(self):
        """Pause or resume the current recording."""
        if self.recording_thread:
            if not self.is_paused:
                # Pause recording
                self.recording_thread.pause_recording()
                self.is_paused = True
                self.pause_button.setText("▶")
                self.pause_button.setToolTip("Resume Recording (F6)")
                self.statusBar().showMessage("Recording paused")
                
                # Pause timer
                self.recording_timer.stop()
            else:
                # Resume recording
                self.recording_thread.resume_recording()
                self.is_paused = False
                self.pause_button.setText("⏸")
                self.pause_button.setToolTip("Pause Recording (F6)")
                self.statusBar().showMessage("Recording resumed")
                
                # Resume timer
                self.recording_timer.start(1000)
                
    def stop_recording(self):
        """Stop the current recording."""
        if self.recording_thread:
            self.recording_timer.stop()
            self.recording_thread.stop_recording()
            self.statusBar().showMessage("Recording stopped")
            
    def stop_and_transcribe(self):
        """Stop the current recording and immediately start transcription."""
        if self.recording_thread:
            # First stop the recording
            self.recording_timer.stop()
            self.recording_thread.stop_recording()
            self.statusBar().showMessage("Recording stopped, starting transcription...")
            
            # Wait a moment for the recording to be saved
            QTimer.singleShot(500, self.check_and_transcribe)
    
    def check_and_transcribe(self):
        """Check if we should transcribe and start transcription if needed."""
        if self.temp_audio_file:
            self.transcribe_audio()
    
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
                self.stop_and_transcribe_button.setEnabled(False)
                self.clear_recording_button.setEnabled(True)
                self.transcribe_button.setEnabled(True)
                self.device_combo.setEnabled(True)
                self.save_default_device_button.setEnabled(True)
                
                # Stop and clear the timer
                if hasattr(self, 'recording_timer'):
                    self.recording_timer.stop()
                
                # Auto-transcribe if enabled
                if self.auto_transcribe_checkbox.isChecked():
                    self.statusBar().showMessage("Recording finished. Auto-transcribing...")
                    QTimer.singleShot(500, self.transcribe_audio)
                else:
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
        
        # Get the selected transformation style
        transformation_style = self.transformation_combo.currentText()
        self.statusBar().showMessage(f"Cleaning up transcription with GPT using {transformation_style} style...")
        
        # Start GPT cleanup
        self.cleanup_thread = CleanupThread(text, transformation_style)
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
                    "default_device_id": None,
                    "default_transformation": "Standard"
                }
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = {
                "api_key": os.environ.get("OPENAI_API_KEY", ""),
                "default_device": None,
                "default_device_id": None,
                "default_transformation": "Standard"
            }
            
    def save_config(self):
        """Save configuration to file."""
        try:
            # Save the current transformation style
            self.config["default_transformation"] = self.transformation_combo.currentText()
            
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
    
    # Set application style
    app.setStyle("Fusion")
    
    window = WhisperNotepadApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
