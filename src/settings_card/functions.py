import copy
import functools
import os.path
import pathlib
from queue import Queue

import numpy as np
from loguru import logger

from supervisely.app.fastapi import run_sync

import supervisely
from supervisely.video_annotation.key_id_map import KeyIdMap

import src.sly_globals as g
from supervisely.app import DataJson

import src.select_class as select_class
import src.select_class.functions as sc_functions

import src.sly_functions as global_functions
import src.dialog_window as dialog_window


def get_bboxes_from_annotation(video_annotation):
    bboxes = []

    video_figure: supervisely.VideoFigure
    for video_figure in video_annotation.figures:
        if video_figure.geometry.geometry_name() == 'rectangle':
            bbox = video_figure.geometry.to_bbox()

            video_figure_id = g.key_id_map.get_figure_id(video_figure.key())

            bboxes.append({
                'label': video_figure.video_object.obj_class.name,
                'bbox': bbox,
                'figureId': video_figure_id,
                'objectId': g.key_id_map.get_object_id(video_figure.video_object.key()),
                'frameIndex': video_figure.frame_index,
            })

            g.video_figure_id_to_video_figure[video_figure_id] = video_figure

    return bboxes


def get_data_to_render(video_info, bboxes, current_dataset):
    data_to_render = []

    for bbox_item in bboxes:
        label = bbox_item['label']

        figure_id = bbox_item['figureId']
        object_id = bbox_item['objectId']
        frame_index = bbox_item['frameIndex']

        bbox = bbox_item['bbox']

        data_to_render.append({
            'figureId': figure_id,
            'objectId': object_id,

            'frameIndex': frame_index,

            'label': label,

            'imageUrl': None,
            'imagePath': None,

            'videoName': f'{video_info.name}',
            'videoId': f'{video_info.id}',
            'frameInClickerUrl': os.path.join(DataJson()["instanceAddress"], f"app/videos/?datasetId={current_dataset.id}&videoFrame={frame_index}&videoId={video_info.id}"),
            'videoHash': f'{video_info.hash}',
            'videoSize': tuple([video_info.frame_width, video_info.frame_height]),

            'datasetName': f'{current_dataset.name}',
            'datasetId': f'{current_dataset.id}',

            'originalBbox': [[bbox.left, bbox.top], [bbox.right, bbox.bottom]],
            'scaledBbox': [[bbox.left, bbox.top], [bbox.right, bbox.bottom]],

            'positivePoints': [],
            'negativePoints': [],
            'mask': None,
            'isActive': True,

            'boxArea': (bbox.right - bbox.left) * (bbox.bottom - bbox.top)
        })

    return data_to_render


def put_data_to_queues(data_to_render):
    for item in data_to_render:
        g.classes2queues.setdefault(item['label'], Queue(maxsize=int(1e6))).put(item)


def get_annotations_for_dataset(dataset_id, videos):
    videos_ids = [video_info.id for video_info in videos]
    return g.api.video.annotation.download_bulk(dataset_id=dataset_id, entity_ids=videos_ids)


def get_crops_for_queue(video_info, video_annotation_json, current_dataset, project_meta):
    video_annotation = supervisely.VideoAnnotation.from_json(video_annotation_json, project_meta, g.key_id_map)

    g.video_hash_to_video_ann[video_info.hash] = video_annotation

    bboxes = get_bboxes_from_annotation(video_annotation)
    data_to_render = get_data_to_render(video_info, bboxes, current_dataset)
    return data_to_render


def create_new_project_by_name(state):
    project_name = f'{g.api.project.get_info_by_id(g.input_project_id).name}_BST'

    created_project = g.api.project.create(workspace_id=DataJson()['workspaceId'],
                                           type=supervisely.ProjectType.VIDEOS,
                                           name=project_name,
                                           change_name_if_conflict=True)

    state['outputProject']['id'] = created_project.id


def create_new_object_meta_by_name(output_class_name, geometry_type):
    objects = supervisely.ObjClassCollection(
        [supervisely.ObjClass(name=output_class_name, geometry_type=geometry_type,
                              color=list(np.random.choice(range(256), size=3)))])

    return supervisely.ProjectMeta(obj_classes=objects, project_type=supervisely.ProjectType.VIDEOS)


def get_object_class_by_name(state, output_class_name, geometry_type=supervisely.AnyGeometry):
    output_project_meta = supervisely.ProjectMeta.from_json(g.api.project.get_meta(id=state['outputProject']['id']))
    obj_class = output_project_meta.obj_classes.get(output_class_name, None)

    while obj_class is None or obj_class.geometry_type is not geometry_type:
        if obj_class is not None and obj_class.geometry_type is not geometry_type:
            output_class_name += '_BST'

        updated_meta = output_project_meta.merge(create_new_object_meta_by_name(output_class_name, geometry_type))
        g.api.project.update_meta(id=state['outputProject']['id'], meta=updated_meta.to_json())

        output_project_meta = supervisely.ProjectMeta.from_json(g.api.project.get_meta(id=state['outputProject']['id']))
        obj_class = output_project_meta.obj_classes.get(output_class_name, None)

    return obj_class


def cache_existing_video_info(state):
    output_project_id = state['outputProject']['id']
    datasets_in_output_project = g.api.dataset.get_list(project_id=output_project_id)

    for current_dataset in datasets_in_output_project:
        videos_infos = g.api.video.get_list(dataset_id=current_dataset.id)

        g.videohash2videoinfo_by_datasets[current_dataset.id] = {video_info.hash: video_info for video_info in
                                                                 videos_infos}


def cache_existing_objects_mapping_in_output_project(state):
    project_custom_data = global_functions.get_project_custom_data(state['outputProject']['id']).get('_batched_smart_tool', {})
    uploaded_objects_mapping = project_custom_data.get('objects_mapping', {})

    for input_object_id, output_object_id in uploaded_objects_mapping.items():
        object_key = g.key_id_map.get_object_key(int(input_object_id))
        if object_key is not None:
            g.output_key_id_map.add_object(object_key, output_object_id)


def cache_existing_data(state):
    cache_existing_video_info(state)
    cache_existing_objects_mapping_in_output_project(state)

    return state


def refill_queues_by_input_project_data(project_id):
    project_meta = supervisely.ProjectMeta.from_json(g.api.project.get_meta(id=project_id))
    g.input_project_meta = project_meta.clone()

    project_datasets = g.api.dataset.get_list(project_id=project_id)

    crops_data = []

    for current_dataset in dialog_window.datasets_progress(project_datasets, message='downloading datasets'):
        videos_in_dataset = g.api.video.get_list(dataset_id=current_dataset.id)
        annotations_in_dataset = get_annotations_for_dataset(dataset_id=current_dataset.id,
                                                             videos=videos_in_dataset)

        for current_video_info, current_annotation in dialog_window.images_progress(
                zip(videos_in_dataset, annotations_in_dataset), total=len(videos_in_dataset),
                message='downloading videos annotations'):
            crops_data.extend(get_crops_for_queue(video_info=current_video_info,
                                                  video_annotation_json=current_annotation,
                                                  current_dataset=current_dataset,
                                                  project_meta=project_meta))

    g.crops_data = crops_data


def select_input_project(identifier: str, state):
    g.grid_controller.clean_all(state=state, data=DataJson())
    refill_queues_by_input_project_data(project_id=identifier)


def select_bboxes_order(state):
    g.crops_data = sorted(g.crops_data, key=lambda d: d['objectId'], reverse=True)
    put_data_to_queues(data_to_render=g.crops_data)

    sc_functions.init_table_data()  # fill classes table

    output_project_id = get_output_project_id()
    if output_project_id is not None:
        state['dialogWindow']['mode'] = 'outputProject'
        state['outputProject']['id'] = output_project_id

        dialog_window.notification_box.title = 'Project with same output name founded'
        dialog_window.notification_box.description = '''
        Output project with name
            <a href="{}/projects/{}/datasets"
                           target="_blank">{}</a> already exists.<br>
            Do you want to use existing project or create a new?
        '''.format(
            DataJson()['instanceAddress'],
            output_project_id,
            f'{g.api.project.get_info_by_id(g.input_project_id).name}_BST')


def update_output_class(state):
    try:
        selected_row = select_class.classes_table.get_selected_row(state)
    except IndexError:
        selected_row = None

    if state['queueMode'] == 'objects' and selected_row is not None:
        g.output_class_name = selected_row[0]
    else:
        g.output_class_name = None


def update_selected_queue(state):
    g.selected_queue = g.classes2queues[g.output_class_name]


def remove_processed_geometries(state):
    custom_data = global_functions.get_project_custom_data(state['outputProject']['id']).get('_batched_smart_tool', {})
    processed_geometries_ids = custom_data.get('processed_figures_ids', [])

    for label, queue in g.classes2queues.items():
        updated_queue = Queue(maxsize=int(1e6))
        for item in queue.queue:
            if item['figureId'] not in processed_geometries_ids:
                updated_queue.put(item)

        g.classes2queues[label] = updated_queue

    select_class.update_classes_table(state)


def get_output_project_id():
    for project in g.api.project.get_list(workspace_id=DataJson()['workspaceId']):
        if project.name == f'{g.api.project.get_info_by_id(g.input_project_id).name}_BST':
            return project.id


def copy_meta_from_input_to_output(output_project_id):
    meta = supervisely.ProjectMeta.from_json(data=g.api.project.get_meta(output_project_id))
    meta = meta.merge(other=g.input_project_meta)
    g.api.project.update_meta(output_project_id, meta.to_json())


def add_tag_to_project_meta(project_id, tag_name):
    project_meta = supervisely.ProjectMeta.from_json(g.api.project.get_meta(project_id))
    tag_meta = supervisely.TagMeta(name=tag_name, value_type=supervisely.TagValueType.ANY_STRING)

    if project_meta.get_tag_meta(tag_name) is None:
        project_meta = project_meta.clone(tag_metas=project_meta.tag_metas.add(tag_meta))
        g.api.project.update_meta(project_id, project_meta.to_json())

        logger.info(f'new tag added to project meta: {project_id=}, {tag_name=}')
    return tag_meta


def get_tag_from_project_meta(project_id, tag_name):
    project_meta = supervisely.ProjectMeta.from_json(g.api.project.get_meta(project_id))
    tag_meta = project_meta.tag_metas.get(tag_name, None)
    if tag_meta is None:
        tag_meta = add_tag_to_project_meta(project_id, tag_name)
    return tag_meta


def convert_annotations_to_bitmaps(state):
    for video_hash, video_annotation in g.video_hash_to_video_ann.items():
        video_objects = []
        for video_object in video_annotation.objects:
            # video_object.obj_class
            obj_class = get_object_class_by_name(state, video_object.obj_class.name)
            video_objects.append(video_object.clone(obj_class=obj_class))
        updated_video_objects = supervisely.VideoObjectCollection(video_objects)
        g.video_hash_to_video_ann[video_hash] = video_annotation.clone(objects=updated_video_objects)

