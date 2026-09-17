import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QTextEdit

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LinkJob AI")
        self.setGeometry(100, 100, 800, 600)

        # Create a central widget and set it
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create a layout
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Create a label
        label = QLabel("Witaj w aplikacji LinkJob AI!", self)
        label.setStyleSheet("font-size: 24px;")
        layout.addWidget(label)

        # Create a text edit widget
        self.text_edit = QTextEdit(self)
        layout.addWidget(self.text_edit)

        # Create a button
        button = QPushButton("Rozpocznij", self)
        button.clicked.connect(self.start_processing)
        layout.addWidget(button)

    def start_processing(self):
        # Get text from the text edit widget
        user_input = self.text_edit.toPlainText()
        # Process the input (for now, just display it in the label)
        label = QLabel(f"Przetworzono: {user_input}", self)
        label.setStyleSheet("font-size: 24px;")
        self.setCentralWidget(label)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
