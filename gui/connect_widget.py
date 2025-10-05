# gui/connect_widget.py
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer

class ConnectWidget(QWidget):
    """启动后显示“正在连接手表...”的界面"""
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        self.label = QLabel("正在连接手表，请稍候...")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)
        self.setLayout(layout)
    
    def set_message(self, text: str):
        self.label.setText(text)