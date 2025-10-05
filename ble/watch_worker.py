# watch-gui/ble/watch_worker.py
import asyncio
import numpy as np
import queue
from threading import Thread
from PyQt5.QtCore import QThread, QObject, pyqtSignal, QTimer
from bleak import BleakScanner, BleakClient

from signal_processing.filters import bandpass_filter, savgol_smooth, NLMSFilter
from signal_processing.rri import RRIProcessor
from signal_processing.normal import normalize_signal

READ_CHAR_UUID = "000034F2-0000-1000-8000-00805F9B34FB"


# ====================================================
# =============== 数据处理线程信号容器 =================
# ====================================================
class DataProcessorSignals(QObject):
    processed_ppg = pyqtSignal(np.ndarray)
    processed_accel = pyqtSignal(np.ndarray)
    hr_updated = pyqtSignal(float)


# ====================================================
# ================== 数据处理线程 =====================
# ====================================================
class DataProcessor(Thread):
    """数据处理线程，负责从队列中获取原始数据并进行滤波、心率计算"""
    def __init__(self, fs=100, buffer_len=2000):
        super().__init__()
        self.fs = fs
        self.buffer_len = buffer_len
        self.running = True
        
        # 信号对象
        self.signals = DataProcessorSignals()
        
        # 线程安全队列（最大100个数据包）
        self.ppg_queue = queue.Queue(maxsize=100)
        self.accel_queue = queue.Queue(maxsize=100)
        
        # 环形缓冲区
        self.ppg_buffer = np.zeros(buffer_len, dtype=np.float32)
        self.accel_buffer = np.zeros((buffer_len, 3), dtype=np.float32)
        self.ppg_index = 0
        self.accel_index = 0
        
        # 信号处理组件
        self.nlms = NLMSFilter()
        self.rri_proc = RRIProcessor(fs=self.fs)
        self.latest_bpm = None

    # ---------------------- 主循环 ----------------------
    def run(self):
        while self.running:
            # 处理 PPG 数据
            try:
                raw_ppg = self.ppg_queue.get(timeout=0.1)
                self._process_ppg(raw_ppg)
                self.ppg_queue.task_done()
            except queue.Empty:
                pass
                
            # 处理 加速度数据
            try:
                accel_data = self.accel_queue.get(timeout=0.1)
                self._process_accel(accel_data)
                self.accel_queue.task_done()
            except queue.Empty:
                pass

    # ---------------------- PPG处理 ----------------------
    def _process_ppg(self, raw_ppg):
        # 1️⃣ 带通滤波
        filtered_ppg = bandpass_filter(raw_ppg, fs=self.fs)
        
        # 2️⃣ 使用 NLMS 去伪影（若有参考加速度数据）
        cleaned_ppg = filtered_ppg
        accel_len = min(self.accel_index, len(filtered_ppg))
        if accel_len >= len(filtered_ppg):
            ref_data = self.get_accel_buffer()[-len(filtered_ppg):]
            cleaned_ppg = np.array([
                self.nlms.adapt(d, ref_data[i].flatten()) 
                for i, d in enumerate(filtered_ppg)
            ], dtype=np.float32)
        
        # 3️⃣ 平滑处理
        cleaned_ppg = savgol_smooth(cleaned_ppg)
        
        # 4️⃣ 更新环形缓冲区
        for d in cleaned_ppg:
            self.ppg_buffer[self.ppg_index % self.buffer_len] = d
            self.ppg_index += 1
            
        # 5️⃣ 计算RRI与心率
        peaks = self.rri_proc.detect_peaks(self.get_ppg_buffer())
        _, bpm = self.rri_proc.compute_rri(peaks)
        if bpm is not None:
            self.latest_bpm = bpm
            self.signals.hr_updated.emit(bpm)
            
        # 6️⃣ 发送处理后信号
        self.signals.processed_ppg.emit(self.get_ppg_buffer())

    # ---------------------- 加速度处理 ----------------------
    def _process_accel(self, data):
        for d in data:
            self.accel_buffer[self.accel_index % self.buffer_len] = d
            self.accel_index += 1
        self.signals.processed_accel.emit(self.get_accel_buffer())

    # ---------------------- 环形缓冲访问 ----------------------
    def get_ppg_buffer(self):
        idx = self.ppg_index % self.buffer_len
        return np.roll(self.ppg_buffer, -idx)

    def get_accel_buffer(self):
        idx = self.accel_index % self.buffer_len
        return np.roll(self.accel_buffer, -idx, axis=0)

    # ---------------------- 停止线程 ----------------------
    def stop(self):
        self.running = False
        self.join()


# ====================================================
# ================== 蓝牙采集线程 =====================
# ====================================================
class WatchWorker(QThread):
    """主线程：负责蓝牙连接、数据接收、GUI更新"""
    
    # 对外信号接口保持不变
    ppg_signal = pyqtSignal(list)
    accel_signal = pyqtSignal(list)
    status_signal = pyqtSignal(str)
    hr_signal = pyqtSignal(float)

    CONNECTION_TIMEOUT = 40
    SCAN_SLEEP_INTERVAL = 1
    SCAN_TIMEOUT = 3

    def __init__(self, device_name="Q31(ID-B4F7)", fs=100, gui_update_interval=50):
        super().__init__()
        self.device_name = device_name
        self.fs = fs
        self.running = True
        self.loop = None
        self.client = None
        
        # 初始化数据处理线程
        self.buffer_len = 20 * self.fs
        self.processor = DataProcessor(fs=fs, buffer_len=self.buffer_len)
        self.processor.signals.processed_ppg.connect(self._on_processed_ppg)
        self.processor.signals.processed_accel.connect(self._on_processed_accel)
        self.processor.signals.hr_updated.connect(self.hr_signal.emit)
        self.processor.start()

        # GUI更新定时器
        self.gui_update_interval = gui_update_interval
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(self.gui_update_interval)

        self.latest_ppg = np.array([], dtype=np.float32)

    # ====================================================
    # ================ 蓝牙数据回调 ========================
    # ====================================================
    async def notification_handler(self, sender, data):
        decoded = self.decode_data(data)
        if not decoded:
            return

        if decoded['type'] == 'ppg':
            raw_ppg = np.array(decoded['data'], dtype=np.float32)
            try:
                self.processor.ppg_queue.put_nowait(raw_ppg)
            except queue.Full:
                self.status_signal.emit("⚠️ PPG队列已满，丢弃数据")

        elif decoded['type'] == 'accel':
            try:
                self.processor.accel_queue.put_nowait(decoded['data'])
            except queue.Full:
                self.status_signal.emit("⚠️ 加速度队列已满，丢弃数据")

    # ====================================================
    # ================ 数据回调接口 ========================
    # ====================================================
    def _on_processed_ppg(self, data):
        self.latest_ppg = normalize_signal(data)

    def _on_processed_accel(self, data):
        self.accel_signal.emit(list(data[-len(data):]))

    # ====================================================
    # ================ GUI 更新 ============================
    # ====================================================
    def update_gui(self):
        if len(self.latest_ppg) > 0:
            self.ppg_signal.emit(list(self.latest_ppg))

    # ====================================================
    # ================ 蓝牙连接与监听 ======================
    # ====================================================
    async def connect_and_listen(self):
        self.status_signal.emit("🔄 正在连接设备...")
        target = None

        # 扫描连接
        start_time = asyncio.get_running_loop().time()
        while True:
            elapsed = asyncio.get_running_loop().time() - start_time
            if elapsed > self.CONNECTION_TIMEOUT:
                self.status_signal.emit("❌ 无法连接手表")
                return

            devices = await BleakScanner.discover(timeout=self.SCAN_TIMEOUT)
            for d in devices:
                if d.name == self.device_name:
                    try:
                        self.client = BleakClient(d)
                        await self.client.connect()
                        if self.client.is_connected:
                            target = self.client
                            self.status_signal.emit("✅ 扫描连接成功")
                            break
                    except Exception as e:
                        self.status_signal.emit(f"连接异常: {e}")
            if target:
                break
            await asyncio.sleep(self.SCAN_SLEEP_INTERVAL)

        # 开始监听数据
        await target.start_notify(READ_CHAR_UUID, self.notification_handler)
        self.status_signal.emit("📡 开始接收数据")
        while self.running:
            await asyncio.sleep(1)

    # ====================================================
    # ================ BLE 数据解码 ========================
    # ====================================================
    def decode_data(self, data):
        command = data[0:2]
        if command == b'\xff\xfa':
            min_len = 10
        elif command == b'\xff\xfb':
            min_len = 14
        else:
            return None
        if len(data) < min_len:
            return None

        timestamp = int.from_bytes(data[2:6], 'little')
        length = data[6]
        crc = data[7 + length]
        calc_crc = 0
        for byte in data[0 : 7 + length]:
            calc_crc ^= byte
        if calc_crc != crc:
            return None

        if command == b'\xff\xfa':
            if length % 2 != 0:
                return None
            ppg_bytes = data[7 : 7 + length]
            points = [int.from_bytes(ppg_bytes[i:i+2], 'little')
                      for i in range(0, len(ppg_bytes), 2)]
            return {'type': 'ppg', 'data': points, 'timestamp': timestamp}
        elif command == b'\xff\xfb':
            if length % 6 != 0:
                return None
            accel_bytes = data[7 : 7 + length]
            points = []
            for i in range(0, len(accel_bytes), 6):
                x = int.from_bytes(accel_bytes[i:i+2], 'little', signed=True)
                y = int.from_bytes(accel_bytes[i+2:i+4], 'little', signed=True)
                z = int.from_bytes(accel_bytes[i+4:i+6], 'little', signed=True)
                points.append((x, y, z))
            return {'type': 'accel', 'data': points, 'timestamp': timestamp}
        return None

    # ====================================================
    # ================ 线程控制 ============================
    # ====================================================
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.connect_and_listen())
        except Exception as e:
            self.status_signal.emit(f"蓝牙线程异常: {e}")

    def stop(self):
        self.running = False
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.processor.stop()
        self.quit()
        self.wait()
