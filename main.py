import sys
from PyQt5.QtWidgets import QApplication
from ble.watch_worker import WatchWorker
from gui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    worker = WatchWorker()
    w = MainWindow(worker)
    w.show()
    sys.exit(app.exec_())
