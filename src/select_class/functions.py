from supervisely.app import DataJson
from src.select_class.local_widgets import classes_table, selected_class_progress
import src.select_class.local_widgets as local_widgets

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


def update_classes_table():
    actual_rows = classes_table.rows

    labels = list(g.classes2queues.keys())
    queues = list(g.classes2queues.values())

    for row in actual_rows:
        label = row[0]
        if label == g.output_class_name:
            row[2] = len(queues[labels.index(label)].queue) + len([widget for widget in g.grid_controller.widgets.values() if widget.is_empty is False])  # left

            update_classes_progress(label=label, total=row[3], n=row[3]-row[2])
        else:
            row[2] = len(queues[labels.index(label)].queue)

        row[1] = get_obj_num_in_queue(queues[labels.index(label)])
        row[4] = int(((row[3] - row[2]) / row[3]) * 100)  # percentage

    classes_table.rows = actual_rows


def shift_queue_by_object_id(selected_queue, direction='next'):
    def get_all_objects_by_id(obj_id):
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

    if not selected_queue.empty():
        if direction == 'next':
            objects_to_shift = get_all_objects_by_id(obj_id=selected_queue.queue[0]['objectId'])
            selected_queue.queue.extend(objects_to_shift)
        elif direction == 'prev':
            objects_to_shift = get_all_objects_by_id(obj_id=selected_queue.queue[-1]['objectId'])
            selected_queue.queue.extendleft(objects_to_shift)







