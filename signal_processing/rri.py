import numpy as np
from scipy.signal import find_peaks, butter, filtfilt

class RRIProcessor:
    """
    改进版 RRI 处理器：
    - 允许心率范围 45-185 BPM
    - 自动滤波、平滑
    - 过滤舒张峰误检
    """

    def __init__(self, fs=100, hr_min=45, hr_max=185):
        self.fs = fs
        self.hr_min = hr_min
        self.hr_max = hr_max
        # 最小峰间距（采样点）
        self.min_distance = int(fs * 60 / hr_max)
        # 最大峰间距，用于异常值过滤（ms）
        self.max_rri_ms = 60_000 / hr_min
        self.last_peaks = []

    # ------------------ 滤波器 ------------------
    def bandpass_filter(self, data, lowcut=0.9, highcut=3.2, order=4):
        nyq = 0.5 * self.fs
        if highcut >= nyq:
            highcut = nyq - 1e-5
        b, a = butter(order, [lowcut/nyq, highcut/nyq], btype='band')
        return filtfilt(b, a, data)

    # ------------------ 峰检测 ------------------
    def detect_peaks(self, ppg_signal):
        """
        检测 PPG 收缩峰，返回索引列表
        """
        if len(ppg_signal) < self.min_distance:
            return []

        # 自适应峰高阈值
        peak_height = np.median(ppg_signal) + 0.5 * np.std(ppg_signal)

        # 初步检测峰
        peaks, properties = find_peaks(
            ppg_signal,
            distance=self.min_distance,
            height=peak_height
        )

        # 删除峰间隔过小的低峰（保留更高峰）
        clean_peaks = []
        for p in peaks:
            if not clean_peaks:
                clean_peaks.append(p)
                continue
            if p - clean_peaks[-1] < self.min_distance:
                # 保留高度更高的峰
                if ppg_signal[p] > ppg_signal[clean_peaks[-1]]:
                    clean_peaks[-1] = p
            else:
                clean_peaks.append(p)

        self.last_peaks = np.array(clean_peaks)
        return self.last_peaks

    # ------------------ 计算 RRI 和 BPM ------------------
    def compute_rri(self, peaks):
        """
        输入峰索引，返回：
        - rr_intervals : ms
        - bpm : 平均心率
        """
        if len(peaks) < 2:
            return np.array([]), None

        rr_intervals = np.diff(peaks) / self.fs * 1000.0  # ms

        # 去除不合理 RRI
        rr_intervals = np.clip(rr_intervals, 60_000/self.hr_max, 60_000/self.hr_min)

        bpm = 60_000 / np.mean(rr_intervals)  # BPM
        return rr_intervals, bpm
