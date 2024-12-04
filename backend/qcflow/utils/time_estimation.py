# from pkg.schemas.menu import Menu
# import itertools
# from typing import Final
# from datetime import timedelta
# from zoneinfo import ZoneInfo
# import datetime
# from qcflow.task.two_qubit_calibration import (
#     condition,
#     create_available_cnot_pair,
#     reduce_bidirection,
# )

# ONE_QUBIT_CALIBRATION_TIME: Final = 22
# TWO_QUBIT_CALIBRATION_TIME: Final = 22


# # def time_estimation(menu: Menu) -> str:
# #     one_qubit_calibration_sequence = len(menu.qubit_index_list)
# #     estimation_time = ONE_QUBIT_CALIBRATION_TIME * one_qubit_calibration_sequence
# #     qubit_index_list = list(itertools.chain.from_iterable(menu.qubit_index_list))
# #     available_cnot_pair = create_available_cnot_pair(qubit_index_list)
# #     available_cnot_pair_target = reduce_bidirection(available_cnot_pair)
# #     available_cnot_pair_target = [
# #         pair
# #         for pair in available_cnot_pair_target
# #         if condition(menu.mux_index_list, pair)
# #     ]
# #     estimation_time += TWO_QUBIT_CALIBRATION_TIME * len(available_cnot_pair_target)
# #     now = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
# #     calc_min = timedelta(minutes=estimation_time)
# #     end_time = now + calc_min
# #     return end_time.isoformat()
