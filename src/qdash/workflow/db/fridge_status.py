from qdash.dbmodel.fridge_status import ChannelInfo, FridgeStatusModel


def get_fridge_status(device_id):
    fridge_status = FridgeStatusModel.find_one(FridgeStatusModel.device_id == device_id).run()
    if fridge_status:
        return fridge_status
    return None


def insert_fridge_status(device_id):
    fridge_status = FridgeStatusModel(
        device_id=device_id,
        ch2=ChannelInfo(status="normal", threshold=5.0),
        ch6=ChannelInfo(status="normal", threshold=0.02),
    )
    fridge_status.insert()
    return fridge_status


def update_fridge_status(device_id, channel, status):
    fridge_status = FridgeStatusModel.find_one(FridgeStatusModel.device_id == device_id).run()
    if channel == 1:
        fridge_status.ch1 = ChannelInfo(status=status, threshold=0.00)
    elif channel == 2:
        fridge_status.ch2 = ChannelInfo(status=status, threshold=5.00)
    elif channel == 5:
        fridge_status.ch5 = ChannelInfo(status=status, threshold=0.00)
    elif channel == 6:
        fridge_status.ch6 = ChannelInfo(status=status, threshold=0.02)
    fridge_status.save()
    return fridge_status
