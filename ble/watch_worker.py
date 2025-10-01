import asyncio
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from bleak import BleakScanner, BleakClient
from signal_processing.filters import bandpass_filter, savgol_smooth, NLMSFilter
from signal_processing.rri import RRIProcessor
from signal_processing.normal import normalize_signal

READ_CHAR_UUID = "000034F2-0000-1000-8000-00805F9B34FB"

class WatchWorker(QThread):
    ppg_signal = pyqtSignal(list)
    accel_signal = pyqtSignal(list)
    status_signal = pyqtSignal(str)
    hr_signal = pyqtSignal(float)

    def __init__(self, device_name="Q31(ID-B4F7)", fs=100, gui_update_interval=50):
        super().__init__()
        self.device_name = device_name
        self.fs = fs
        self.running = True
        self.loop = None
        self.client = None

        # 环形缓冲区 10秒
        self.buffer_len = 10 * self.fs
        self.ppg_buffer = np.zeros(self.buffer_len, dtype=np.float32)
        self.accel_buffer = np.zeros((self.buffer_len, 3), dtype=np.float32)
        self.ppg_index = 0
        self.accel_index = 0

        self.nlms = NLMSFilter()
        self.rri_proc = RRIProcessor(fs=self.fs)

        # GUI 限频更新
        self.gui_update_interval = gui_update_interval  # ms
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(self.gui_update_interval)

        self.latest_ppg = np.array([], dtype=np.float32)

    # -------------------- 数据处理 --------------------
    def add_ppg(self, data):
        for d in data:
            self.ppg_buffer[self.ppg_index % self.buffer_len] = d
            self.ppg_index += 1

    def add_accel(self, data):
        for d in data:
            self.accel_buffer[self.accel_index % self.buffer_len] = d
            self.accel_index += 1

    async def notification_handler(self, sender, data):
        decoded = self.decode_data(data)
        if not decoded:
            return

        if decoded['type'] == 'ppg':
            raw_ppg = np.array(decoded['data'], dtype=np.float32)
            filtered_ppg = bandpass_filter(raw_ppg, fs=self.fs)
            cleaned_ppg = []
            accel_len = min(self.accel_index, len(filtered_ppg))
            if accel_len >= len(filtered_ppg):
                ref_data = self.accel_buffer[(self.accel_index - len(filtered_ppg)) % self.buffer_len:]
                for i, d in enumerate(filtered_ppg):
                    x_ref = ref_data[:i+1, :].flatten()
                    cleaned_ppg.append(self.nlms.adapt(d, x_ref))
            else:
                cleaned_ppg = filtered_ppg
            cleaned_ppg = savgol_smooth(cleaned_ppg)
            self.add_ppg(cleaned_ppg)

            # RRI 心率计算
            peaks = self.rri_proc.detect_peaks(self.get_ppg_buffer())
            _, bpm = self.rri_proc.compute_rri(peaks)
            if bpm is not None:
                self.hr_signal.emit(bpm)

        elif decoded['type'] == 'accel':
            self.add_accel(decoded['data'])
            self.accel_signal.emit(decoded['data'])

    def decode_data(self, data):
        if len(data) < 8:
            return None
        command = data[0:2]
        if command == b'\xff\xfa':
            ppg_bytes = data[7:-1]
            points = [int.from_bytes(ppg_bytes[i:i+2], 'little') 
                      for i in range(0, len(ppg_bytes), 2) if i+1 < len(ppg_bytes)]
            return {'type': 'ppg', 'data': points}
        elif command == b'\xff\xfb':
            accel_bytes = data[7:-1]
            points = []
            for i in range(0, len(accel_bytes), 6):
                if i+5 < len(accel_bytes):
                    x = int.from_bytes(accel_bytes[i:i+2], 'little', signed=True)
                    y = int.from_bytes(accel_bytes[i+2:i+4], 'little', signed=True)
                    z = int.from_bytes(accel_bytes[i+4:i+6], 'little', signed=True)
                    points.append((x, y, z))
            return {'type': 'accel', 'data': points}
        return None

    # -------------------- 缓冲区读取 --------------------
    def get_ppg_buffer(self):
        # 获取按时间顺序排列的 PPG 缓冲区
        idx = self.ppg_index % self.buffer_len
        return np.concatenate((self.ppg_buffer[idx:], self.ppg_buffer[:idx]))

    def get_accel_buffer(self):
        idx = self.accel_index % self.buffer_len
        return np.concatenate((self.accel_buffer[idx:], self.accel_buffer[:idx]))

    # -------------------- GUI 更新 --------------------
    def update_gui(self):
        if self.ppg_index == 0:
            return
        self.latest_ppg = normalize_signal(self.get_ppg_buffer())
        self.ppg_signal.emit(list(self.latest_ppg))

    # -------------------- 蓝牙连接 --------------------
    async def connect_and_listen(self):
        self.status_signal.emit("正在连接设备...")
        if self.client and self.client.is_connected:
            target = self.client
        else:
            devices = await BleakScanner.discover(timeout=5)
            target = None
            for d in devices:
                if d.name == self.device_name:
                    self.client = BleakClient(d)
                    await self.client.connect()
                    if self.client.is_connected:
                        target = self.client
                        self.status_signal.emit("扫描连接成功")
                        break
        if not target:
            self.status_signal.emit("无法连接手表")
            return

        await target.start_notify(READ_CHAR_UUID, self.notification_handler)
        self.status_signal.emit("开始接收数据")
        while self.running:
            await asyncio.sleep(1)

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.connect_and_listen())
        except Exception as e:
            self.status_signal.emit(f"蓝牙线程异常: {e}")

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.stop()
        self.quit()
        self.wait()
