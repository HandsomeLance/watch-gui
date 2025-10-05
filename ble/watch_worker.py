import asyncio
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from bleak import BleakScanner, BleakClient
from signal_processing.filters import bandpass_filter, savgol_smooth, NLMSFilter
from signal_processing.rri import RRIProcessor
from signal_processing.normal import normalize_signal

READ_CHAR_UUID = "000034F2-0000-1000-8000-00805F9B34FB"

class WatchWorker(QThread):
    CONNECTION_TIMEOUT = 40  # seconds
    SCAN_SLEEP_INTERVAL = 1  # seconds
    SCAN_TIMEOUT = 3  # seconds

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
        self.loop = None
        self.client = None

        # 环形缓冲区 20秒
        self.buffer_len = 20 * self.fs
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

        # 心率更新
        self.hr_update_interval = 5000  # 毫秒，5秒
        self.hr_timer = QTimer()
        self.hr_timer.timeout.connect(self.update_hr)
        self.hr_timer.start(self.hr_update_interval)
        self.latest_bpm = None  # 缓存心率

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
                self.latest_bpm = bpm

        elif decoded['type'] == 'accel':
            self.add_accel(decoded['data'])
            self.accel_signal.emit(decoded['data'])

    def decode_data(self, data):
        # 1. 按指令类型判断最小长度（符合文档结构推算）
        command = data[0:2]
        min_len = 0
        if command == b'\xff\xfa':
            min_len = 10  # PPG最小包长度：2+4+1+2+1=10
        elif command == b'\xff\xfb':
            min_len = 14  # 三轴最小包长度：2+4+1+6+1=14
        else:
            return None  # 指令头非法
        
        if len(data) < min_len:
            return None  # 长度不足，直接返回无效

        # 2. 提取公共字段（时间戳、数据长度、CRC，符合文档）
        timestamp = int.from_bytes(data[2:6], 'little')  # 三轴指令补全时间戳提取
        length = data[6]
        crc = data[7 + length]  # 提取CRC位（业务数据后1字节）
        
        # 3. CRC校验（严格按文档“异或规则”）
        calc_crc = 0
        for byte in data[0 : 7 + length]:  # 校验位前所有字节
            calc_crc ^= byte
        if calc_crc != crc:
            return None  # CRC校验失败，数据无效

        # 4. 业务数据截取与合法性校验（符合文档倍数要求）
        if command == b'\xff\xfa':  # PPG数据
            if length % 2 != 0:
                return None  # 文档要求PPG长度为2的倍数
            ppg_bytes = data[7 : 7 + length]
            points = [int.from_bytes(ppg_bytes[i:i+2], 'little') 
                    for i in range(0, len(ppg_bytes), 2)]
            return {'type': 'ppg', 'data': points, 'timestamp': timestamp}  # 返回时间戳供连续性判断
        
        elif command == b'\xff\xfb':  # 三轴数据
            if length % 6 != 0:
                return None  # 文档要求三轴长度为6的倍数
            accel_bytes = data[7 : 7 + length]
            points = []
            for i in range(0, len(accel_bytes), 6):
                x = int.from_bytes(accel_bytes[i:i+2], 'little', signed=True)
                y = int.from_bytes(accel_bytes[i+2:i+4], 'little', signed=True)
                z = int.from_bytes(accel_bytes[i+4:i+6], 'little', signed=True)
                points.append((x, y, z))
            return {'type': 'accel', 'data': points, 'timestamp': timestamp}  # 补全时间戳返回

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

    # -------------------- 心率更新 --------------------
    def update_hr(self):
        if self.latest_bpm is not None:
            self.hr_signal.emit(self.latest_bpm)

    # -------------------- 蓝牙连接 --------------------
    async def connect_and_listen(self):
        self.status_signal.emit("正在连接设备...")

        # 如果已经连接，直接使用
        if self.client and self.client.is_connected:
            target = self.client
        else:
            target = None
            start_time = asyncio.get_running_loop().time()  # 记录开始时间
            while True:
                elapsed = asyncio.get_running_loop().time() - start_time
                if elapsed > self.CONNECTION_TIMEOUT:  # 超过 CONNECTION_TIMEOUT 秒仍未连接
                    self.status_signal.emit("无法连接手表")
                    return
                # 扫描设备，timeout=3s
                devices = await BleakScanner.discover(timeout=self.SCAN_TIMEOUT)
                for d in devices:
                    if d.name == self.device_name:
                        try:
                            self.client = BleakClient(d)
                            await self.client.connect()
                            if self.client.is_connected:
                                target = self.client
                                self.status_signal.emit("扫描连接成功")
                                break
                        except Exception as e:
                            self.status_signal.emit(f"尝试连接异常: {e}")
                if target:
                    break  # 找到目标设备并成功连接后跳出循环
                await asyncio.sleep(self.SCAN_SLEEP_INTERVAL)  # 每轮扫描间隔 SCAN_SLEEP_INTERVAL 秒

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
