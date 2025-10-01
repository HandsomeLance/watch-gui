import asyncio
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from bleak import BleakScanner, BleakClient
from signal_processing.filters import bandpass_filter, savgol_smooth, NLMSFilter
from signal_processing.rri import RRIProcessor

READ_CHAR_UUID = "000034F2-0000-1000-8000-00805F9B34FB"

class WatchWorker(QThread):
    ppg_signal = pyqtSignal(list)
    accel_signal = pyqtSignal(list)
    status_signal = pyqtSignal(str)
    hr_signal = pyqtSignal(float)

    def __init__(self, device_name="Q31(ID-B4F7)"):
        super().__init__()
        self.device_name = device_name
        self.loop = None
        self.client = None
        self.running = True
        self.fs = 100
        self.nlms = NLMSFilter()
        self.ppg_buffer = []
        self.accel_buffer = []

        self.rri_proc = RRIProcessor(fs=self.fs)

    async def notification_handler(self, sender, data):
        decoded = self.decode_data(data)
        if not decoded:
            return
        if decoded['type'] == 'ppg':
            raw_ppg = np.array(decoded['data'], dtype=np.float32)
            filtered_ppg = bandpass_filter(raw_ppg, fs=self.fs)
            cleaned_ppg = []
            if len(self.accel_buffer) >= len(filtered_ppg):
                ref_data = np.array(self.accel_buffer[-len(filtered_ppg):])
                for i, d in enumerate(filtered_ppg):
                    x_ref = ref_data[:i+1, :].flatten()
                    cleaned_ppg.append(self.nlms.adapt(d, x_ref))
            else:
                cleaned_ppg = filtered_ppg
            cleaned_ppg = savgol_smooth(cleaned_ppg)
            self.ppg_buffer.extend(cleaned_ppg)
            if len(self.ppg_buffer) > 500:
                self.ppg_buffer = self.ppg_buffer[-500:]
            self.ppg_signal.emit(list(self.ppg_buffer))
            # --- RRI峰值检测 + 心率 ---
            peaks = self.rri_proc.detect_peaks(self.ppg_buffer)
            _, bpm = self.rri_proc.compute_rri(peaks)
            if bpm is not None:
                self.hr_signal.emit(bpm)
        elif decoded['type'] == 'accel':
            self.accel_buffer.extend(decoded['data'])
            self.accel_signal.emit(decoded['data'])

    def decode_data(self, data):
        if len(data) < 8:
            return None
        command = data[0:2]
        if command == b'\xff\xfa':
            ppg_bytes = data[7:-1]
            points = [int.from_bytes(ppg_bytes[i:i+2], 'little') for i in range(0, len(ppg_bytes), 2) if i+1 < len(ppg_bytes)]
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

    async def connect_and_listen(self):
        self.status_signal.emit("正在连接设备...")
        if self.client and self.client.is_connected:
            self.status_signal.emit("已连接，接收数据中")
            target = self.client
        else:
            devices = await BleakScanner.discover(timeout=5)
            target = None
            for d in devices:
                if d.name == self.device_name:
                    self.client = BleakClient(d)
                    await self.client.connect()
                    if self.client.is_connected:
                        self.status_signal.emit("扫描连接成功")
                        target = self.client
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
