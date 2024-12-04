from dbmodel.menu import MenuModel
from lib.init_db import init_db


def generate_menu():
    return MenuModel(
        name="SAMPLE",
        description="sample description",
        one_qubit_calib_plan=[
            [0, 1, 2, 3],
            [4, 5, 6, 7],
            [8, 9, 10, 11],
            [12, 13, 14, 15],
            [16, 17, 18, 19],
            [20, 21, 22, 23],
            [24, 25, 26, 27],
            [28, 29, 30, 31],
        ],
        two_qubit_calib_plan=[[[0, 1], [2, 3]], [[4, 5], [6, 7]]],
        mode="default",
        notify_bool=True,
        tags=["routine"],
        flow=["one-qubit-calibration-flow"],
        exp_list=["Example1"],
    )


def init_menu():
    init_db()
    generate_menu().insert()


def delete_menu():
    init_db()
    MenuModel.delete_all()


if __name__ == "__main__":
    init_menu()
