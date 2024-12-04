import os

from prefect import task


@task(name="create directory")
def create_directory_task(calib_dir: str):
    if not os.path.exists(calib_dir):
        os.makedirs(calib_dir)
    path_list = [
        f"{calib_dir}/calib_full",
        f"{calib_dir}/fig_tdm",
        f"{calib_dir}/calib_full_jazz",
        f"{calib_dir}/calib_full_jazz_half_pi",
        f"{calib_dir}/fig_jazz",
        f"{calib_dir}/fig_cr",
        f"{calib_dir}/calib_cr",
    ]
    for path in path_list:
        if not os.path.exists(path):
            os.mkdir(path)
