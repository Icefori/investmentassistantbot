EXCHANGES_FOREIGN = {"NASDAQ", "AMEX", "LSE", "NYSE"}
EXCHANGES_KZ = {"KASE", "AIX"}

def calc_fees(exchange: str, qty: int, price: float, is_sell: bool = False) -> dict:
    """
    Возвращает словарь с комиссиями: br_fee, ex_fee, cp_fee, sum, end_pr.
    - exchange: биржа (строка)
    - qty: количество бумаг (int, всегда положительное)
    - price: цена одной бумаги (float)
    - is_sell: True если продажа, False если покупка

    Любая биржа, кроме KASE и AIX, считается иностранной.
    """
    exchange = (exchange or "").upper()
    br_fee = 0.0
    ex_fee = 0.0
    cp_fee = 0.0

    if exchange not in EXCHANGES_KZ:
        if not is_sell:
            cp_fee = max(0.01 * qty, 7.5)
            br_fee = 0.001 * qty * price
            ex_fee = 0.0
        else:
            cp_fee = 0.0
            ex_fee = 0.0001 * qty + 0.000072 * qty
            br_fee = 0.001 * qty * price
    else:
        br_fee = 0.0003 * qty * price
        ex_fee = 0.0
        cp_fee = 0.0

    # Округление до двух знаков после запятой
    br_fee = round(br_fee, 2)
    ex_fee = round(ex_fee, 2)
    cp_fee = round(cp_fee, 2)

    # Абсолютная сумма сделки (qty * price + все комиссии)
    sum_value = round(qty * price + br_fee + ex_fee + cp_fee, 2)
    # Итоговая цена за 1 бумагу с учетом комиссий
    end_pr = round(sum_value / qty, 4) if qty else 0.0

    return {
        "br_fee": br_fee,
        "ex_fee": ex_fee,
        "cp_fee": cp_fee,
        "sum": sum_value,
        "end_pr": end_pr
    }