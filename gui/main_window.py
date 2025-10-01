from PyQt5.QtWidgets import QMainWindow
from gui.plot_widget import PPGPlotWidget

class MainWindow(QMainWindow):
    def __init__(self, worker):
        super().__init__()
        self.setWindowTitle("手表实时PPG监测")
        self.plot_widget = PPGPlotWidget()
        self.setCentralWidget(self.plot_widget)

        self.statusBar().showMessage("等待连接...")

        self.worker = worker
        self.worker.ppg_signal.connect(self.plot_widget.update_data)
        self.worker.status_signal.connect(self.update_status)
        self.worker.hr_signal.connect(self.update_hr)
        self.worker.start()

    def update_status(self, msg: str):
        self.statusBar().showMessage(msg)

    def update_hr(self, bpm):
        self.statusBar().showMessage(f"心率: {bpm:.1f} BPM")

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()
