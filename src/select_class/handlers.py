import traceback

from fastapi import Depends, HTTPException

import supervisely

from supervisely.app import DataJson
from supervisely.app.fastapi import run_sync

import src.grid_controller.handlers as grid_controller_handlers

import src.sly_globals as g
import src.sly_functions as f

import src.select_class.functions as local_functions
import src.select_class.widgets as local_widgets


def select_another_object(flag: str,
                          state: supervisely.app.StateJson = Depends(supervisely.app.StateJson.from_request)):
    g.grid_controller.update_local_fields(state=state, data=DataJson())
    g.grid_controller.clean_all(state=state, data=DataJson(), images_queue=g.selected_queue)

    local_functions.shift_queue_by_object_id(selected_queue=g.selected_queue, direction=flag)

    f.put_n_frames_to_queue(g.selected_queue)

    grid_controller_handlers.windows_count_changed(state=state)

    state['anotherObjectLoading'] = False
    run_sync(state.synchronize_changes())


def show_mark_object_dialog(state: supervisely.app.StateJson = Depends(supervisely.app.StateJson.from_request)):
    local_widgets.mark_object_as_unlabeled_notification.title = f'Object with ID {state["selectedObjectId"]} will be skipped'
    local_widgets.mark_object_as_unlabeled_notification.description = f'All {DataJson()["figuresLeftQueue"]} figures will be marked as unlabeled'

    state['dialogWindow']['mode'] = 'markObjectAsUnlabeled'
    run_sync(DataJson().synchronize_changes())
    run_sync(state.synchronize_changes())


def mark_object_as_unlabeled(state: supervisely.app.StateJson = Depends(supervisely.app.StateJson.from_request)):
    object_id_to_mark = state['selectedObjectId']
    figures_left = DataJson()["figuresLeftQueue"]
    try:
        g.grid_controller.update_local_fields(state=state, data=DataJson())
        g.grid_controller.clean_all(state=state, data=DataJson(), images_queue=g.selected_queue)

        broken_objects = local_functions.get_broken_objects_by_obj_id(obj_id=object_id_to_mark, queue=g.selected_queue)

        ds_name_to_objects = {}
        for broken_object in broken_objects:
            if isinstance(broken_object['datasetName'], str):
                ds_name_to_objects.setdefault(broken_object['datasetName'], []).append(broken_object)

        for ds_name, broken_objects_in_dataset in ds_name_to_objects.items():
            ds_id = f.get_dataset_id_by_name(ds_name, state['outputProject']['id'])
            f.upload_figures_to_dataset(dataset_id=ds_id, data_to_upload=broken_objects_in_dataset)

        grid_controller_handlers.windows_count_changed(state=state)
    except Exception as ex:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail={'title': "Exception occurred",
                                                     'message': f'{ex}'})

    finally:
        # state['slyNotification'] = {  #  @TODO: ask Umar why it doesn't work
        #     'type': 'success',
        #     'title': 'Done',
        #     'message': f'All {figures_left} figures were marked as unlabeled',
        #     'duration': 2
        # }
        state['queueIsEmpty'] = g.selected_queue.empty()
        state['markingObjectLoading'] = False
        state['dialogWindow']['mode'] = ''
        run_sync(state.synchronize_changes())
