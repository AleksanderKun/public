from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout
from PyQt5.QtCore import Qt


class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(100, 100, 300, 100)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.suggestion_label = QLabel("AI SUGESTIA", self)
        self.suggestion_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.suggestion_label)

        self.close_button = QPushButton("Zamknij", self)
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)

    def set_suggestion(self, suggestion: str):
        self.suggestion_label.setText(suggestion)
