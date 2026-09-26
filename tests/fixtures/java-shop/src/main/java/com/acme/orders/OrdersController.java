package com.acme.orders;

import com.acme.orders.domain.Order;

@RequestMapping("/orders")
public class OrdersController {
    @GetMapping("/{id}")
    public Order find() { return null; }
}
