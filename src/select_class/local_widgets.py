import supervisely.app.widgets as widgets


def progress_bar_formatter(value):
    return f'''<el-progress 
                    :percentage="{value}" 
                    :text-inside="true"
                    :stroke-width="18" style="width: 170px">
                    </el-progress>'''


classes_table = widgets.RadioTable(
    columns=["classname", "objects left", "figures left", "figures total", "progress"],
    rows=[],
    subtitles={},  # {"name": "subname"},
    column_formatters={
        'progress': progress_bar_formatter
    },
)


selected_class_progress = widgets.SlyTqdm()
running_classes_progress = None
