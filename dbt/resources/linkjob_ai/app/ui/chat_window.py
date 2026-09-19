from PyQt5.QtWidgets import (
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
)
from PyQt5.QtCore import Qt
from ..conversation_service import ConversationService
from ..config import Config


class ChatWindow(QMainWindow):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.conversation_service = ConversationService(config)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("LinkJob AI Chat")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        self.conversation_list = QListWidget()
        layout.addWidget(self.conversation_list)

        self.message_display = QTextEdit()
        self.message_display.setReadOnly(True)
        layout.addWidget(self.message_display)

        self.message_input = QLineEdit()
        layout.addWidget(self.message_input)

        self.send_button = QPushButton("Send")
        layout.addWidget(self.send_button)

        self.send_button.clicked.connect(self.send_message)
        self.message_input.returnPressed.connect(self.send_message)

        self.load_conversations()

    def load_conversations(self):
        conversations = self.conversation_service.list_conversations(
            user_id=1
        )  # Assuming user_id is hardcoded for simplicity
        for conversation in conversations:
            item = QListWidgetItem(conversation.title)
            item.setData(Qt.UserRole, conversation.id)
            self.conversation_list.addItem(item)

    def send_message(self):
        current_item = self.conversation_list.currentItem()
        if current_item:
            conversation_id = current_item.data(Qt.UserRole)
            content = self.message_input.text()
            if content:
                self.conversation_service.send_message(
                    conversation_id, content, sender="user", user_id=1
                )  # Assuming user_id is hardcoded for simplicity
                self.message_input.clear()
                self.load_messages(conversation_id)

    def load_messages(self, conversation_id):
        messages = self.conversation_service.get_messages(
            conversation_id, user_id=1
        )  # Assuming user_id is hardcoded for simplicity
        self.message_display.clear()
        for message in messages:
            self.message_display.append(f"{message.sender}: {message.content}")
