"""Local deterministic demo service. Data resets on process restart."""

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


class OrderInput(BaseModel):
    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=100)


def create_app():
    app = FastAPI(title='Orders Demo API', version='1.0.0')
    orders = {}

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/orders')
    def list_orders(limit: int = Query(default=20, ge=1, le=100)):
        return list(orders.values())[:limit]

    @app.post('/orders', status_code=201)
    def create_order(payload: OrderInput):
        if payload.quantity > 3:
            raise HTTPException(status_code=409, detail='Insufficient stock')
        order = {'id': str(uuid4()), 'status': 'created', **payload.model_dump()}
        orders[order['id']] = order
        return order

    @app.get('/orders/{order_id}')
    def get_order(order_id: str):
        if order_id not in orders:
            raise HTTPException(status_code=404, detail='Order not found')
        return orders[order_id]

    return app


app = create_app()
