"""Chat routes — extracted from main.py."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from database.memory_store import (
    create_chat_conversation,
    delete_chat_conversation,
    get_chat_messages,
    list_chat_conversations,
    verify_conversation_ownership,
)
from services.chat_service import execute_confirmed_action as chat_execute_action
from services.chat_service import process_message as chat_process_message

router = APIRouter(prefix="/chat", tags=["Chat"])


class NewChatRequest(BaseModel):
    conversation_id: str | None = None
    title: str | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    title: str | None = None


class ChatConfirmRequest(BaseModel):
    conversation_id: str
    tool_name: str
    args: dict[str, Any]


@router.post("/new")
def chat_new(req: NewChatRequest, request: Request = None):
    uid = getattr(request.state, "user_id", "") if request else ""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    cid = req.conversation_id or str(uuid.uuid4())
    create_chat_conversation(conversation_id=cid, title=req.title or "New Chat", workspace_id=ws_id, user_id=uid)
    return {"ok": True, "conversation_id": cid}


@router.post("")
def chat_endpoint(req: ChatRequest, request: Request = None):
    uid = getattr(request.state, "user_id", "") if request else ""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    cid = req.conversation_id
    if not cid:
        cid = create_chat_conversation(title=req.title or "New Chat", workspace_id=ws_id, user_id=uid)
    result = chat_process_message(req.message, cid, workspace_id=ws_id)
    result["conversation_id"] = cid
    return result


@router.post("/confirm-action")
def chat_confirm_action(req: ChatConfirmRequest, request: Request = None):
    result = chat_execute_action(req.conversation_id, req.tool_name, req.args)
    result["conversation_id"] = req.conversation_id
    return result


@router.get("/conversations")
def chat_list_conversations(request: Request = None):
    uid = getattr(request.state, "user_id", "") if request else ""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    convos = list_chat_conversations(workspace_id=ws_id, user_id=uid, limit=20)
    return {"conversations": convos}


@router.get("/conversations/{conversation_id}/messages")
def chat_get_messages(conversation_id: str, limit: int = 50, request: Request = None):
    uid = getattr(request.state, "user_id", "") if request else ""
    if uid and not verify_conversation_ownership(conversation_id, uid):
        return {"messages": []}
    msgs = get_chat_messages(conversation_id, limit=limit)
    return {"messages": msgs}


@router.delete("/conversations/{conversation_id}")
def chat_delete_conversation(conversation_id: str, request: Request = None):
    uid = getattr(request.state, "user_id", "") if request else ""
    if uid and not verify_conversation_ownership(conversation_id, uid):
        return {"ok": False}
    ok = delete_chat_conversation(conversation_id)
    return {"ok": ok}