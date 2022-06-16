import functools
import os
import threading

from supervisely.app.fastapi import run_sync
from loguru import logger

import src.sly_functions as global_functions

def process_with_lock(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        self.lock.acquire(timeout=5)
        ret_val = func(self, *args, **kwargs)
        self.lock.release()
        return ret_val

    return wrapper


class GridController:
    def __init__(self, origin_widget_class):
        self.lock = threading.Lock()
        self._origin_widget_class = origin_widget_class
        self.widgets = {}

    @process_with_lock
    def change_count(self, actual_count, app, state, data, images_queue):
        while actual_count > len(self.widgets) and not images_queue.empty():
            self._add(app, state, data, images_queue)

        while actual_count < len(self.widgets):
            self._remove(state, data, images_queue)

    # @process_with_lock
    def change_padding(self, actual_padding):
        for widget in self.widgets.values():
            if not widget.is_empty and not widget.is_broken and not widget.is_finished:
                widget.clean_up()
                widget.add_bbox_padding(padding_coefficient=actual_padding)

    def get_widget_by_id(self, widget_id):
        return self.widgets[widget_id]

    # @process_with_lock
    def update_local_fields(self, state, data):
        for widget in self.widgets.values():
            widget.update_local_fields(state=state, data=data)

    @process_with_lock
    def update_remote_fields(self, state, data):
        for widget in self.widgets.values():
            if not widget.is_empty:
                widget.update_remote_fields(state=state, data=data, synchronize=False)

        run_sync(state.synchronize_changes())

    # @process_with_lock
    def _add(self, app, state, data, images_queue):
        widget = self._origin_widget_class(app, state, data)
        widget.is_active = False

        if not images_queue.empty():
            widget.is_active = True
            new_data = images_queue.get()

            if new_data['imageUrl'] is None or os.path.isfile(new_data['imagePath']) is False:
                file_path, file_url = global_functions.download_frame_from_video_with_cache(
                    video_id=new_data['videoId'],
                    frame_index=new_data['frameIndex']
                )

                new_data['filePath'] = file_path.as_posix()
                new_data['imageUrl'] = file_url.as_posix()

            widget.update_fields_by_data(new_data)
            if not widget.is_empty:
                widget.add_bbox_padding(padding_coefficient=state['bboxesPadding'])
                widget.change_mask_opacity(opacity_coefficient=state['masksOpacity'])

        self.widgets[widget.identifier] = widget

    # @process_with_lock
    def _remove(self, state, data, images_queue):
        identifiers = list(self.widgets.keys())
        if len(identifiers) > 0:
            last_object = self.widgets.pop(identifiers[-1])

            if images_queue is not None:
                images_queue.queue.appendleft(last_object.get_data_to_send())
            else:
                if os.path.isfile(last_object.image_path):
                    os.remove(last_object.image_path)

            last_object.remove_remote_fields(state=state, data=data)

    @process_with_lock
    def clean_all(self, state, data, images_queue=None):
        identifiers = list(self.widgets.keys())
        while len(identifiers) > 0:
            self._remove(state, data, images_queue)
            identifiers = list(self.widgets.keys())
        run_sync(state.synchronize_changes())
