import numpy as np
from scipy.signal import find_peaks

class RRIProcessor:
    def __init__(self, fs=100, min_peak_distance_sec=0.5):
        self.fs = fs
        self.min_distance = int(min_peak_distance_sec * fs)
        self.last_peaks = []
    
    def detect_peaks(self, ppg_signal):
        """
        检测PPG波峰
        返回波峰索引列表
        """
        if len(ppg_signal) < self.min_distance:
            return []
        peaks, _ = find_peaks(ppg_signal, distance=self.min_distance)
        self.last_peaks = peaks
        return peaks

    def compute_rri(self, peaks):
        """
        计算RRI(ms) 和心率(BPM)
        """
        if len(peaks) < 2:
            return [], None
        rr_intervals = np.diff(peaks) / self.fs * 1000.0  # ms
        bpm = 60.0 / (np.mean(rr_intervals)/1000.0)      # BPM
        return rr_intervals, bpm
