from decimal import Decimal, ROUND_HALF_UP

EXCHANGES_KZ = {"KASE", "AIX"}

def quant2(val):
    return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def quant4(val):
    return Decimal(val).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

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
    br_fee = Decimal("0.00")
    ex_fee = Decimal("0.00")
    cp_fee = Decimal("0.00")

    qty = Decimal(qty)
    price = Decimal(str(price))

    if exchange not in EXCHANGES_KZ:
        if not is_sell:
            cp_fee = quant2(max(Decimal("0.01") * qty, Decimal("7.5")))
            br_fee = quant2(Decimal("0.001") * qty * price)
            ex_fee = Decimal("0.00")
        else:
            cp_fee = Decimal("0.00")
            ex_fee = quant2(Decimal("0.0001") * qty + Decimal("0.000072") * qty)
            br_fee = quant2(Decimal("0.001") * qty * price)
    else:
        br_fee = quant2(Decimal("0.0003") * qty * price)
        ex_fee = Decimal("0.00")
        cp_fee = Decimal("0.00")

    sum_value = quant2(abs(qty * price) + br_fee + ex_fee + cp_fee)
    end_pr = quant4(sum_value / abs(qty)) if qty else Decimal("0.0000")

    return {
        "br_fee": br_fee,
        "ex_fee": ex_fee,
        "cp_fee": cp_fee,
        "sum": sum_value,
        "end_pr": end_pr
    }