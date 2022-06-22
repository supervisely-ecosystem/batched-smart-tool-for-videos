from supervisely.app import DataJson
from src.select_class.widgets import classes_table, selected_class_progress
import src.select_class.widgets as local_widgets

import src.sly_globals as g


def update_classes_progress(label, total, n):
    if local_widgets.running_classes_progress is None:
        local_widgets.running_classes_progress = selected_class_progress(total=int(total),
                                                                         message=f'annotating {label}',
                                                                         initial=int(n))
    else:
        local_widgets.running_classes_progress.n = int(n)
        local_widgets.running_classes_progress.refresh()


def init_table_data():
    rows_to_init = []
    for label, queue in g.classes2queues.items():
        objects_num = get_obj_num_in_queue(queue)
        rows_to_init.append([label, objects_num, len(queue.queue), len(queue.queue), 0])

    classes_table.rows = rows_to_init


def get_obj_num_in_queue(queue):
    obj_ids = set()

    for queue_elem in queue.queue:
        obj_ids.add(queue_elem.get('objectId'))

    return len(obj_ids)


def update_classes_table(state):
    actual_rows = classes_table.rows

    labels = list(g.classes2queues.keys())
    queues = list(g.classes2queues.values())

    for index, row in enumerate(actual_rows):
        label, objects_left, figures_left, figures_total, progress_n = row
        objects_left = get_obj_num_in_queue(queues[labels.index(label)])

        if label == g.output_class_name:
            figures_left = len(queues[labels.index(label)].queue) + len([widget for widget in g.grid_controller.widgets.values() if widget.is_empty is False])  # left
            update_classes_progress(label=label, total=figures_total, n=figures_total-figures_left)

            if not queues[labels.index(label)].empty() and state['selectedObjectId'] is not None:
                figures_left_in_queue = len([widget_data for widget_data in queues[labels.index(label)].queue
                                        if widget_data['objectId'] == state['selectedObjectId']])

                figures_left_on_screen = len([widget for widget in g.grid_controller.widgets.values() if widget.is_empty is False])

                if figures_left_in_queue == 0:
                    objects_left += 1

                DataJson()['figuresLeftQueue'] = figures_left_in_queue + figures_left_on_screen  # left current object id left
            else:
                DataJson()['figuresLeftQueue'] = 0

            DataJson()['objectsLeftTotal'] = figures_total
            DataJson()['objectsLeftQueue'] = objects_left

        else:
            figures_left = len(queues[labels.index(label)].queue)

        progress_n = int(((figures_total - figures_left) / figures_total) * 100)  # percentage

        actual_rows[index] = [label, objects_left, figures_left, figures_total, progress_n]



    classes_table.rows = actual_rows


def get_all_objects_by_id(obj_id, selected_queue, direction='next'):
    obj_list = []
    while not selected_queue.empty():
        if direction == 'next':
            if selected_queue.queue[0]['objectId'] == obj_id:
                obj_list.append(selected_queue.get())
            else:
                break
        else:
            if selected_queue.queue[-1]['objectId'] == obj_id:
                obj_list.append(selected_queue.queue.pop())
            else:
                break
    return obj_list


def shift_queue_by_object_id(selected_queue, direction='next'):
    if not selected_queue.empty():
        if direction == 'next':
            objects_to_shift = get_all_objects_by_id(obj_id=selected_queue.queue[0]['objectId'], selected_queue=selected_queue, direction=direction)
            selected_queue.queue.extend(objects_to_shift)
        elif direction == 'prev':
            objects_to_shift = get_all_objects_by_id(obj_id=selected_queue.queue[-1]['objectId'], selected_queue=selected_queue, direction=direction)
            selected_queue.queue.extendleft(objects_to_shift)


def get_broken_objects_by_obj_id(obj_id, queue):
    objects_data = get_all_objects_by_id(obj_id, queue)
    for current_object in objects_data:
        current_object['isBroken'] = True
    return objects_data
