import asyncio
import functools
import os
import pathlib
import time
import uuid

import jinja2
import numpy as np
from starlette.templating import Jinja2Templates
from supervisely.video_annotation.video_tag_collection import VideoTagCollection
from supervisely.video_annotation.video_tag import VideoTag

import supervisely

import src.sly_globals as g

import src.select_class as select_class
from supervisely.app import DataJson


def get_supervisely_video_figure_by_widget_data(widget_data):
    video_figure: supervisely.VideoFigure = g.video_figure_id_to_video_figure.get(widget_data['figureId'], None)

    if widget_data.get('isBroken', False) and widget_data.get('originalBbox') is not None:
        original_bbox = widget_data['originalBbox']
        geometry = supervisely.Rectangle(
            top=original_bbox[0][1], left=original_bbox[0][0],
            bottom=original_bbox[1][1], right=original_bbox[1][0]
        )

        not_labeled_tag = VideoTag(
            g.broken_tag_meta,
            value='not annotated',
            frame_range=[widget_data['frameIndex'], widget_data['frameIndex']]
        )

        video_object = video_figure.video_object.clone(obj_class=g.output_class_object,
                                                       tags=VideoTagCollection([not_labeled_tag]))

        return video_figure.clone(video_object=video_object, geometry=geometry)

    if video_figure is not None and widget_data.get('mask') is not None and widget_data.get('originalBbox') is not None:
        mask_np = supervisely.Bitmap.base64_2_data(widget_data['mask']['data'])
        geometry = supervisely.Bitmap(data=mask_np,
                                      origin=supervisely.PointLocation(row=widget_data['mask']['origin'][1],
                                                                       col=widget_data['mask']['origin'][0]))

        video_object = video_figure.video_object.clone(obj_class=g.output_class_object)
        # video_object = supervisely.VideoObject(obj_class=g.output_class_object)

        return video_figure.clone(video_object=video_object, geometry=geometry)


def get_project_custom_data(project_id):
    project_info = g.api.project.get_info_by_id(project_id)
    if project_info.custom_data:
        return project_info.custom_data
    else:
        return {}


def append_processed_video_figures(figures_ids, project_id):
    project_custom_data = get_project_custom_data(project_id).get('_batched_smart_tool', {})
    project_custom_data.setdefault('processed_figures_ids', []).extend(figures_ids)
    g.api.project.update_custom_data(project_id, {'_batched_smart_tool': project_custom_data})


def upload_objects_mapping_to_custom_data(project_id):
    project_custom_data = get_project_custom_data(project_id).get('_batched_smart_tool', {})
    uploaded_objects_mapping = project_custom_data.get('objects_mapping', {})

    output_mapping = g.output_key_id_map.to_dict()['objects']
    input_mapping = g.key_id_map.to_dict()['objects']

    for key, value in output_mapping.items():
        uploaded_objects_mapping[input_mapping[key]] = output_mapping[key]

    project_custom_data['objects_mapping'] = uploaded_objects_mapping
    g.api.project.update_custom_data(project_id, {'_batched_smart_tool': project_custom_data})


def get_frame_collection(video_figures) -> supervisely.FrameCollection:
    frame_index_to_figures = {}

    for video_figure in video_figures:  # collect by frames
        frame_index_to_figures.setdefault(video_figure.frame_index, []).append(video_figure)

    frames_list = []
    for frame_index, figures_on_frame in frame_index_to_figures.items():
        frames_list.append(supervisely.Frame(frame_index, figures_on_frame))

    return supervisely.FrameCollection(frames_list)


def upload_broken_objects_tags(video_info, video_figures):
    broken_objects_list = [video_figure.video_object for video_figure in video_figures]
    g.api.video.tag.append_to_objects(
        entity_id=video_info.id,
        project_id=g.output_project_id,
        objects=broken_objects_list,
        key_id_map=g.output_key_id_map
    )


def upload_figures_to_dataset(dataset_id, data_to_upload):
    hash2annotation = {}
    hash_to_video_figures = {}
    hash_to_video_names = {}

    for widget_data in data_to_upload:
        video_figure = get_supervisely_video_figure_by_widget_data(widget_data)
        if video_figure is not None:
            hash_to_video_figures.setdefault(widget_data['videoHash'], []).append(video_figure)
            hash_to_video_names[widget_data['videoHash']] = widget_data['videoName']

    for video_hash, video_figures in hash_to_video_figures.items():
        if len(video_figures) > 0:
            videohash2videoinfo = g.videohash2videoinfo_by_datasets.get(dataset_id, {})
            video_info = videohash2videoinfo.get(video_hash)

            frame_collection = get_frame_collection(video_figures)

            if video_info is None:  # if image not founded in hashed images
                video_info = g.api.video.upload_hash(
                    dataset_id=dataset_id,
                    name=f'{hash_to_video_names[video_hash]}',
                    hash=video_hash
                )

                g.videohash2videoinfo_by_datasets.setdefault(dataset_id, {})[video_hash] = video_info
                annotation = g.video_hash_to_video_ann[video_hash].clone(frames=frame_collection)

                g.api.video.annotation.append(video_info.id, annotation, g.output_key_id_map)
                upload_broken_objects_tags(video_info, video_figures)
                upload_objects_mapping_to_custom_data(project_id=g.output_project_id)
            else:
                annotation = g.video_hash_to_video_ann[video_hash].clone(objects=[], frames=frame_collection)
                g.api.video.annotation.append(video_info.id, annotation, g.output_key_id_map)
                upload_broken_objects_tags(video_info, video_figures)

    append_processed_video_figures(
        figures_ids=[item['figureId'] for item in data_to_upload if item['figureId'] is not None],
        project_id=g.output_project_id)

    return hash2annotation


@functools.lru_cache(maxsize=8)
def get_dataset_id_by_name(current_dataset_name, output_project_id):
    datasets_in_project = g.api.dataset.get_list(output_project_id)

    for current_dataset in datasets_in_project:
        if current_dataset.name == current_dataset_name:
            return current_dataset.id

    created_ds = g.api.dataset.create(project_id=output_project_id, name=current_dataset_name)
    return created_ds.id


def objects_left_number():
    obj_counter = 0
    for queue in g.classes2queues.values():
        obj_counter += len(queue.queue)
    return obj_counter


def update_queues_stats(state):
    state['selectClassVisible'] = False
    state['outputClassName'] = g.output_class_name
    state['updatingClass'] = False

    DataJson()['objectsLeftTotal'] = objects_left_number()
    DataJson()['objectsLeftQueue'] = len(g.selected_queue.queue)

    select_class.update_classes_table()  # @TODO: update table by objects ids


# @functools.lru_cache(maxsize=32)
def download_frame_from_video_with_cache(video_id, frame_index) -> (pathlib.Path, pathlib.Path):
    filename = f'{video_id}_{frame_index}.png'

    file_path = g.temp_frames_dir / filename

    if file_path.exists() is False:
        g.api.video.frame.download_path(
            video_id=video_id,
            frame_index=frame_index,
            path=file_path.as_posix()
        )
    return file_path, pathlib.Path('./static', 'temp_frames', filename)


def put_n_frames_to_queue(queue, n=1):
    for index, item in enumerate(queue.queue):
        if item['imageUrl'] is None or item['imagePath'] is None or os.path.isfile(item['imagePath']) is False:
            file_path, file_url = download_frame_from_video_with_cache(
                video_id=item['videoId'],
                frame_index=item['frameIndex']
            )
            item.update({
                'imageUrl': file_url.as_posix(),
                'imagePath': file_path.as_posix()
            })
            queue.queue[index] = item

        if index == n:
            break
