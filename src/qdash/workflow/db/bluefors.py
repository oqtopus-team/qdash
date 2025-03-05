from datetime import datetime, timezone

from qdash.dbmodel.bluefors import BlueforsModel


def get_latest_temperature(device_id, channel_nr):
    latest_record = BlueforsModel.find_one(
        BlueforsModel.device_id == device_id,
        BlueforsModel.channel_nr == channel_nr,
        sort=[("timestamp", -1)],
    ).run()
    if latest_record is not None:
        return latest_record.temperature
    else:
        return 0


def upsert_metrics(data, device_id):
    fields = data["fields"]
    measurements = data["measurements"]
    num_measurements = len(measurements["timestamp"])
    transformed_data: list[BlueforsModel] = []
    for i in range(num_measurements):
        record = {field: measurements[field][i] for field in fields}
        r = BlueforsModel(
            id=f"{device_id}_{data['channel_nr']}_{record['timestamp']}",
            device_id=device_id,
            timestamp=datetime.fromtimestamp(record["timestamp"], tz=timezone.utc),
            resistance=record["resistance"],
            reactance=record["reactance"],
            temperature=record["temperature"],
            rez=record["rez"],
            imz=record["imz"],
            magnitude=record["magnitude"],
            angle=record["angle"],
            channel_nr=data["channel_nr"],
        )
        transformed_data.append(r)
    for d in transformed_data:
        existing_record = BlueforsModel.get(d.id).run()
        if not existing_record:
            d.insert()


# def get_existing_record(id: str):
#     existing_record = BlueforsModel.get(id).run()
#     print(existing_record)
#     return existing_record


# def save_record(record: BlueforsModel):
#     record.save()
#     print(record)
