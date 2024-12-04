# from dbmodel.session_info import SessionInfoModel

# from qcflow.schema.session_info import SessionInfo


# def get_session_info(username: str) -> SessionInfo:
#     session_info = SessionInfoModel.find_one(
#         SessionInfoModel.experiment_username == username
#     ).run()

#     if session_info is None:
#         raise Exception("SessionInfo is not found.")

#     return SessionInfo(
#         labrad_hostname=session_info.labrad_hostname,
#         labrad_username=session_info.labrad_username,
#         labrad_password=session_info.labrad_password,
#         cooling_down_id=session_info.cooling_down_id,
#         experiment_username=session_info.experiment_username,
#         package_name=session_info.package_name,
#     )
