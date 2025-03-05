# import datetime
# from datetime import timedelta

# from prefect import flow
# from prefect.deployments import run_deployment
# from qdash.workflow.schema.menu import Menu
# from qdash.workflow.utils.slack import SlackContents, Status
# from zoneinfo import ZoneInfo


# @flow(name="scheduler", log_prints=True)
# def scheduler_flow(menu: Menu):
#     now = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
#     calc_min = timedelta(minutes=1)
#     target = now + calc_min
#     contents = SlackContents(
#         status=Status.RUNNING,
#         title="scheduler",
#         msg=f"{target.isoformat()}",
#         notify=True,
#         ts="",
#         path="",
#     )
#     contents.send_slack()
#     run_deployment(name="main/main", parameters={"menu": menu}, scheduled_time=target)
