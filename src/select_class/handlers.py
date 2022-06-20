from fastapi import Depends

import supervisely

from supervisely.app import DataJson
from supervisely.app.fastapi import run_sync

import src.grid_controller.handlers as grid_controller_handlers

import src.sly_globals as g
import src.sly_functions as f

import src.select_class.functions as local_functions


def select_another_object(flag: str, state: supervisely.app.StateJson = Depends(supervisely.app.StateJson.from_request)):
    g.grid_controller.update_local_fields(state=state, data=DataJson())
    g.grid_controller.clean_all(state=state, data=DataJson(), images_queue=g.selected_queue)

    local_functions.shift_queue_by_object_id(selected_queue=g.selected_queue, direction=flag)

    f.put_n_frames_to_queue(g.selected_queue)

    grid_controller_handlers.windows_count_changed(state=state)

    state['anotherObjectLoading'] = False
    run_sync(state.synchronize_changes())
