from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from .conversation_service import ConversationService
from .config import Config
from .conversation import Conversation, Message

router = APIRouter()


def get_conversation_service(config: Config = Depends(Config)):
    return ConversationService(config)


@router.post("/conversations/", response_model=Conversation)
def create_conversation(
    title: str,
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    return conversation_service.create_conversation(
        title, user_id=1
    )  # Assuming user_id is hardcoded for simplicity


@router.get("/conversations/", response_model=List[Conversation])
def list_conversations(
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    return conversation_service.list_conversations(
        user_id=1
    )  # Assuming user_id is hardcoded for simplicity


@router.get("/conversations/{conversation_id}", response_model=Conversation)
def get_conversation(
    conversation_id: int,
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    conversation = conversation_service.get_conversation(
        conversation_id, user_id=1
    )  # Assuming user_id is hardcoded for simplicity
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return conversation


@router.get("/conversations/{conversation_id}/messages", response_model=List[Message])
def get_messages(
    conversation_id: int,
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    return conversation_service.get_messages(
        conversation_id, user_id=1
    )  # Assuming user_id is hardcoded for simplicity


@router.put("/conversations/{conversation_id}/title", response_model=Conversation)
def rename_conversation(
    conversation_id: int,
    new_title: str,
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    conversation = conversation_service.rename_conversation(
        conversation_id, new_title, user_id=1
    )  # Assuming user_id is hardcoded for simplicity
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return conversation


@router.delete(
    "/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_conversation(
    conversation_id: int,
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    if not conversation_service.delete_conversation(
        conversation_id, user_id=1
    ):  # Assuming user_id is hardcoded for simplicity
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return None


@router.post("/conversations/{conversation_id}/messages", response_model=Message)
def send_message(
    conversation_id: int,
    content: str,
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    message = conversation_service.send_message(
        conversation_id, content, sender="user", user_id=1
    )  # Assuming user_id is hardcoded for simplicity
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return message


@router.post("/conversations/{conversation_id}/generate", response_model=str)
def generate_ai_response(
    conversation_id: int,
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    response = conversation_service.generate_ai_response(
        conversation_id, user_id=1
    )  # Assuming user_id is hardcoded for simplicity
    if not response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return response
