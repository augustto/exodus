# ruff: noqa


def open_orders(cursor):
    cursor.execute("SELECT id, total FROM orders WHERE status = 'open'")
    return cursor.fetchall()
