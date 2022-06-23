import asyncio
import functools
from threading import Thread

import uvicorn  # 🪐 server tools
from fastapi import Request, Depends

import supervisely
from smart_tool import SmartTool  # 🤖 widgets

import src.initialize_app as initialize_app
import src.sly_globals as g
from supervisely.app import StateJson, DataJson


@g.app.get("/")
def read_index(request: Request):
    return g.templates_env.TemplateResponse('index.html', {'request': request,
                                                           'smart_tool': SmartTool})


@g.app.post("/apply_changes/")
async def apply_changes(state: StateJson = Depends(StateJson.from_request)):
    await state.synchronize_changes()

# @TODO: move broken_tag from objects to figures (SDK request)
# @TODO: figures left / total, objects left / total


@g.app.on_event("startup")
async def startup_event():
    initialize_app.init_routes()
    initialize_app.init_project()

    await StateJson().synchronize_changes()
    await DataJson().synchronize_changes()

