import numpy as np
from scipy.signal import butter, lfilter, savgol_filter

def butter_bandpass(lowcut, highcut, fs, order=4):
    nyq = 0.5 * fs
    b, a = butter(order, [lowcut / nyq, highcut / nyq], btype="band")
    return b, a

def bandpass_filter(data, lowcut=0.5, highcut=4.5, fs=100, order=4):
    b, a = butter_bandpass(lowcut, highcut, fs, order)
    return lfilter(b, a, data)

def savgol_smooth(data, window_length=11, polyorder=3):
    if len(data) >= window_length:
        return savgol_filter(data, window_length, polyorder)
    return data

class NLMSFilter:
    def __init__(self, filter_order=8, mu=0.01, eps=1e-6):
        self.n = filter_order
        self.mu = mu
        self.eps = eps
        self.w = np.zeros(self.n)

    def adapt(self, d, x):
        x = np.array(x[-self.n:][::-1])
        if len(x) < self.n:
            return d
        x = x.reshape(-1)
        norm_x = np.dot(x, x) + self.eps
        y = np.dot(self.w, x)
        e = d - y
        self.w += self.mu * e * x / norm_x
        return e
