"""
Simplified Windows audio capture module
Works without comtypes - provides basic functionality
"""

import numpy as np
import queue

class WindowsLoopbackCapture:
    """Simple dummy implementation when comtypes is not available"""
    def __init__(self, sample_rate=48000, channels=2, chunk_size=1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.is_recording = False
        self.audio_queue = queue.Queue()
        
    def list_devices(self):
        """Return empty list - no devices available without comtypes"""
        return []
        
    def start_recording(self, device_id=None):
        """Cannot start recording without comtypes"""
        return False
        
    def stop_recording(self):
        """Nothing to stop"""
        self.is_recording = False
        
    def get_audio_data(self):
        """No data available"""
        return None

class WindowsAudioCapture:
    """Simple dummy implementation when comtypes is not available"""
    def __init__(self, sample_rate=16000, channels=1, chunk_size=1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.loopback_capture = WindowsLoopbackCapture(
            sample_rate=sample_rate,
            channels=channels,
            chunk_size=chunk_size
        )
        
    def start_loopback_recording(self, device_id=None):
        """Cannot record without comtypes"""
        raise Exception("Windows loopback capture requires comtypes. Install with: pip install comtypes")
        
    def stop_loopback_recording(self):
        """Nothing to stop"""
        if self.loopback_capture:
            self.loopback_capture.stop_recording()
            
    def get_loopback_audio(self):
        """No audio available"""
        return None
        
    def list_loopback_devices(self):
        """No devices available"""
        return []
