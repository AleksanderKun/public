import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LinkJob AI")
        self.setGeometry(100, 100, 800, 600)

        label = QLabel("Witaj w aplikacji LinkJob AI!", self)
        label.setGeometry(100, 100, 600, 100)
        label.setStyleSheet("font-size: 24px;")

        button = QPushButton("Rozpocznij", self)
        button.setGeometry(350, 300, 100, 50)
        button.clicked.connect(self.start_processing)

        self.setCentralWidget(label)

    def start_processing(self):
        label = QLabel("Przetwarzanie danych...", self)
        label.setGeometry(100, 100, 600, 100)
        label.setStyleSheet("font-size: 24px;")
        self.setCentralWidget(label)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
