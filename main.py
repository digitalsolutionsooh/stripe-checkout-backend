from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import stripe
import time
import hashlib
import requests

app = FastAPI()

# CORS
origins = ["https://learnmoredigitalcourse.com"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Env vars
STRIPE_SECRET_KEY   = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET      = os.getenv("STRIPE_WEBHOOK_SECRET")
PIXEL_ID            = os.getenv("PIXEL_ID")
ACCESS_TOKEN        = os.getenv("ACCESS_TOKEN")

@app.get("/health")
async def health():
    return {"status": "up"}

@app.post("/ping")
async def ping():
    return {"pong": True}

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request):
    stripe.api_key = STRIPE_SECRET_KEY

    body = await request.json()
    price_id = body.get("price_id")
    quantity = body.get("quantity", 1)
    utms = { k: body.get(k, "") for k in ("utm_source","utm_medium","utm_campaign","utm_term","utm_content") }

    if not price_id:
        return JSONResponse(status_code=400, content={"error": "price_id is required"})

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{'price': price_id, 'quantity': quantity}],
        mode='payment',
        success_url='https://learnmoredigitalcourse.com/pink-up1-stripe',
        cancel_url='https://learnmoredigitalcourse.com/erro',
        metadata=utms,
        payment_intent_data={"setup_future_usage": "off_session"},
        expand=["line_items"]
    )

    # Conversions API: InitiateCheckout
    event_payload = {
      "data": [{
        "event_name":    "InitiateCheckout",
        "event_time":    int(time.time()),
        "event_id":      session.id,
        "action_source": "website",
        "event_source_url": str(request.url),
        "user_data": {
          "client_ip_address": request.client.host,
          "client_user_agent": request.headers.get("user-agent")
        },
        "custom_data": {
          "currency": session.currency,
          "value":    session.amount_total / 100.0,
          "content_ids": [item.price.id for item in session.line_items.data],
          "content_type": "product"
        }
      }]
    }
    requests.post(
      f"https://graph.facebook.com/v14.0/{PIXEL_ID}/events",
      params={"access_token": ACCESS_TOKEN},
      json=event_payload
    )

    return {"checkout_url": session.url}

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = stripe.checkout.Session.retrieve(
            event["data"]["object"]["id"], expand=["line_items"]
        )
        cust = session["customer"]

        product_ids = [ item.price.product for item in session.line_items.data ]
        if "prod_SiUIZzdFIN9fmS" in product_ids:
            stripe.InvoiceItem.create(
                customer=cust,
                amount=session.amount_total,
                currency=session.currency,
                description="Purchase by Digital Solutions"
            )
            stripe.Invoice.create(
                customer=cust,
                auto_advance=True,
                template="inrtem_1Rn7qKEHsMKn9uopWdZN8xlL"
            )
            
        # Conversions API: Purchase
        email_hash = hashlib.sha256(
            session.customer_details.email.encode('utf-8')
        ).hexdigest()
        purchase_payload = {
          "data": [{
            "event_name":    "Purchase",
            "event_time":    int(time.time()),
            "event_id":      session.id,
            "action_source": "website",
            "event_source_url": session.url,
            "user_data": {"em": email_hash},
            "custom_data": {
              "currency": session.currency,
              "value":    session.amount_total / 100.0,
              "content_ids": [li.price.id for li in session.line_items.data],
              "content_type": "product"
            }
          }]
        }
        requests.post(
          f"https://graph.facebook.com/v14.0/{PIXEL_ID}/events",
          params={"access_token": ACCESS_TOKEN},
          json=purchase_payload
        )

    return JSONResponse({"received": True})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)