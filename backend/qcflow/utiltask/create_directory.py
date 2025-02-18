import os

from prefect import task


@task(name="create directory")
def create_directory_task(calib_dir: str):
    if not os.path.exists(calib_dir):
        os.makedirs(calib_dir)
    path_list = [
        f"{calib_dir}/task",
        f"{calib_dir}/fig",
        f"{calib_dir}/calib",
    ]
    for path in path_list:
        if not os.path.exists(path):
            os.mkdir(path)
