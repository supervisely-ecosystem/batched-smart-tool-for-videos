import functools
from threading import Thread

from supervisely.app.fastapi import run_sync

from supervisely.app import StateJson, DataJson

import src.batched_smart_tool as batched_smart_tool
import src.dialog_window as dialog_window
import src.grid_controller as grid_controller
import src.select_class as select_class
import src.settings_card as settings_card

import src.sly_globals as g
import src.sly_functions as f


def init_routes():
    g.app.add_api_route('/select-output-project/', settings_card.select_output_project, methods=["POST"])
    g.app.add_api_route('/select-output-class/', settings_card.select_output_class, methods=["POST"])

    g.app.add_api_route('/connect-to-model/{identifier}', settings_card.connect_to_model, methods=["POST"])
    g.app.add_api_route('/windows-count-changed/', grid_controller.windows_count_changed, methods=["POST"])

    g.app.add_api_route('/bboxes-padding-changed/', batched_smart_tool.bboxes_padding_changed, methods=["POST"])
    g.app.add_api_route('/bboxes-masks-opacity-changed/', batched_smart_tool.bboxes_masks_opacity_changed,
                        methods=["POST"])

    g.app.add_api_route('/update-locals/', batched_smart_tool.update_locals, methods=["POST"])

    g.app.add_api_route('/change-all-buttons/{is_active}', batched_smart_tool.change_all_buttons, methods=["POST"])
    g.app.add_api_route('/clean-up/', batched_smart_tool.clean_up, methods=["POST"])
    g.app.add_api_route('/assign-base-points/', batched_smart_tool.assign_base_points, methods=["POST"])
    g.app.add_api_route('/update-masks/', batched_smart_tool.update_masks, methods=["POST"])
    g.app.add_api_route('/next-batch/', batched_smart_tool.next_batch, methods=["POST"])

    g.app.add_api_route('/spawn-unsaved-mask-dialog/', dialog_window.spawn_unsaved_mask_dialog, methods=["POST"])

    g.app.add_api_route('/widgets/smarttool/negative-updated/{identifier}', batched_smart_tool.points_updated,
                        methods=["POST"])
    g.app.add_api_route('/widgets/smarttool/positive-updated/{identifier}', batched_smart_tool.points_updated,
                        methods=["POST"])
    g.app.add_api_route('/widgets/smarttool/bbox-updated/{identifier}', batched_smart_tool.bbox_updated,
                        methods=["POST"])


def _init_project(state):
    settings_card.select_input_project(identifier=f'{g.input_project_id}', state=state)  # download input project

    state['inputProject']['loading'] = False
    state['inputProject']['previewUrl'] = g.api.project.get_info_by_id(g.input_project_id).reference_image_url.replace('%3F', '')

    settings_card.select_bboxes_order(state=state)
    if settings_card.get_output_project_id() is None:
        settings_card.select_output_project(state=state)

    run_sync(state.synchronize_changes())
    run_sync(DataJson().synchronize_changes())


def init_project():
    threaded_function = functools.partial(_init_project, state=StateJson())
    thread = Thread(target=threaded_function)
    thread.start()
