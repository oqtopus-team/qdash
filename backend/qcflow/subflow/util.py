import re


def convert_qid(qid: str) -> str:
    """
    Convert QXX to XX. e.g. "Q0" -> "0" "Q01" -> "1"
    """
    if re.fullmatch(r"Q\d+", qid):
        qid = qid[1:]
        return qid
    else:
        raise ValueError("Invalid qid format.")


def convert_label(qid: str) -> str:
    """
    Convert QXX to QXX. e.g. "0" -> "Q0"
    """
    if re.fullmatch(r"\d+", qid):
        qid = "Q" + qid
        return qid
    else:
        raise ValueError("Invalid qid format.")
