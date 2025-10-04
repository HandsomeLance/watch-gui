import numpy as np
from scipy.signal import find_peaks, butter, filtfilt

# 滤波器函数
def butter_bandpass(lowcut, highcut, fs, order=5):
    nyq = 0.5 * fs
    if highcut >= nyq:
        highcut = nyq - 1e-5
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a

def butter_lowpass(highcut, fs, order=5):
    nyq = 0.5 * fs
    if highcut >= nyq:
        highcut = nyq - 1e-5
    high = highcut / nyq
    b, a = butter(order, high, btype='low')
    return b, a

def bandpass_filter(data, lowcut, highcut, fs, order=5):
    if lowcut == 0:
        b, a = butter_lowpass(highcut, fs, order=order)
    else:
        b, a = butter_bandpass(lowcut, highcut, fs, order=order)
    y = filtfilt(b, a, data)
    return y

# RRI Processor
class RRIProcessor:
    def __init__(self, fs=100, min_peak_distance_sec=0.5):
        self.fs = fs
        self.min_distance = int(min_peak_distance_sec * fs)
        self.last_peaks = []

    def detect_peaks(self, ppg_signal):
        """
        先对 PPG 信号进行 0-3Hz 带通滤波，再检测波峰
        返回波峰索引列表
        """
        if len(ppg_signal) < self.min_distance:
            return []

        # 0-3 Hz 带通滤波
        filtered = bandpass_filter(ppg_signal, lowcut=0.0, highcut=3.0, fs=self.fs, order=4)

        # 峰值检测
        peaks, _ = find_peaks(filtered, distance=self.min_distance)

        self.last_peaks = peaks
        return peaks

    def compute_rri(self, peaks):
        """
        计算RRI(ms) 和心率(BPM)
        """
        if len(peaks) < 2:
            return [], None
        rr_intervals = np.diff(peaks) / self.fs * 1000.0  # ms
        bpm = 60.0 / (np.mean(rr_intervals) / 1000.0)     # BPM
        return rr_intervals, bpm