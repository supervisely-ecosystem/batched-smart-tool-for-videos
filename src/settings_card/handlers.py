import copy
from queue import Queue

from loguru import logger

from supervisely.app.fastapi import run_sync
from fastapi import Request, Depends

import src.sly_functions as f
import src.sly_globals as g
import supervisely
from src.select_class import local_widgets
from supervisely.app import DataJson, StateJson

import src.settings_card.functions as local_functions

import src.grid_controller.handlers as grid_controller_handlers

import src.sly_functions as global_functions

import src.dialog_window as dialog_window


def connect_to_model(identifier: str,
                     request: Request,
                     state: supervisely.app.StateJson = Depends(supervisely.app.StateJson.from_request)):
    try:
        response = g.api.task.send_request(int(state['processingServer']['sessionId']), "is_online",
                                           data={},
                                           context={}, timeout=1)
        if response['is_online'] is not True:
            raise ConnectionError

        state['processingServer']['connected'] = True
    except Exception as ex:
        dialog_window.notification_box.title = 'Cannot connect to model.'
        dialog_window.notification_box.description = 'Please choose another model.'
        state['dialogWindow']['mode'] = 'modelConnection'
        state['processingServer']['connected'] = False

    state['processingServer']['loading'] = False
    run_sync(state.synchronize_changes())
    run_sync(DataJson().synchronize_changes())


def select_output_project(state: supervisely.app.StateJson = Depends(supervisely.app.StateJson.from_request)):
    g.imagehash2imageinfo_by_datasets = {}  # reset output images cache
    g.grid_controller.clean_all(state=state, data=DataJson(), images_queue=g.selected_queue)

    if state['outputProject']['mode'] == 'new':
        local_functions.create_new_project_by_name(state)
        local_functions.copy_meta_from_input_to_output(state['outputProject']['id'])
        g.broken_tag_meta = local_functions.add_tag_to_project_meta(project_id=state['outputProject']['id'],
                                                                    tag_name='_not_labeled_by_BTC')
    else:
        state['outputProject']['id'] = local_functions.get_output_project_id()
        local_functions.cache_existing_data(state)
        local_functions.remove_processed_geometries(state)

        g.broken_tag_meta = local_functions.get_tag_from_project_meta(project_id=state['outputProject']['id'],
                                                                      tag_name='_not_labeled_by_BTC')

    g.output_project_id = state['outputProject']['id']
    local_functions.update_output_class(state)

    if g.output_class_name is not None:
        select_output_class(state=state)  # selecting first class from table
    else:
        state['queueIsEmpty'] = True

    local_functions.convert_annotations_to_bitmaps(state=state)

    state['outputProject']['loading'] = False
    state['dialogWindow']['mode'] = None

    run_sync(state.synchronize_changes())
    run_sync(DataJson().synchronize_changes())


def select_output_class(state: supervisely.app.StateJson = Depends(supervisely.app.StateJson.from_request)):
    local_functions.update_output_class(state)
    local_widgets.running_classes_progress = None

    g.grid_controller.update_local_fields(state=state, data=DataJson())
    g.grid_controller.clean_all(state=state, data=DataJson(), images_queue=g.selected_queue)

    g.output_class_object = local_functions.get_object_class_by_name(state, g.output_class_name)

    local_functions.update_selected_queue(state)
    state['queueIsEmpty'] = g.selected_queue.empty()
    global_functions.put_n_frames_to_queue(g.selected_queue)

    grid_controller_handlers.windows_count_changed(state=state)
    run_sync(state.synchronize_changes())
