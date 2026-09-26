# ruff: noqa

from shop.models import Order


@app.get("/orders")
def orders() -> list[Order]:
    return []
