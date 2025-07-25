from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import stripe

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "up"}

@app.post("/ping")
async def ping():
    return {"pong": True}

origins = [
    "https://learnmoredigitalcourse.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/create-checkout-session")
async def create_checkout_session(request: Request):
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

    WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

    @app.post("/webhook")
    async def stripe_webhook(request: Request):
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        try:
            event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:
            return JSONResponse(status_code=400, content={"error": "Invalid webhook signature"})

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            cust = session["customer"]

            # 1) registra o item de fatura
            stripe.InvoiceItem.create(
                customer=cust,
                amount=session["amount_total"],
                currency=session["currency"],
                description="Purchase by Digital Solutions"
            )

            # 2) recupera os produtos da sessão
            line_items = stripe.checkout.Session.list_line_items(
                session["id"], limit=10
            ).data
            products = [ li.price.product for li in line_items ]

            # 3) escolhe o template de fatura se for o produto alvo
            if "prod_SiUIZzdFIN9fmS" in products:
                invoice = stripe.Invoice.create(
                    customer=cust,
                    auto_advance=True,
                    template="inrtem_1Rn7qKEHsMKn9uopWdZN8xlL"
                )
            else:
                invoice = stripe.Invoice.create(
                    customer=cust,
                    auto_advance=True
                )

        return JSONResponse(status_code=200, content={"received": True})

    if not stripe.api_key:
        return JSONResponse(status_code=500, content={"error": "Stripe Secret Key não encontrada no ambiente."})

    body = await request.json()

    price_id = body.get("price_id")
    quantity = body.get("quantity", 1)

    utms = {
        "utm_source": body.get("utm_source", ""),
        "utm_medium": body.get("utm_medium", ""),
        "utm_campaign": body.get("utm_campaign", ""),
        "utm_term": body.get("utm_term", ""),
        "utm_content": body.get("utm_content", "")
    }

    if not price_id:
        return JSONResponse(status_code=400, content={"error": "price_id is required"})

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': quantity,
            }],
            mode='payment',
            success_url='https://learnmoredigitalcourse.com/pink-up1-stripe',
            cancel_url='https://learnmoredigitalcourse.com/erro',
            metadata=utms,
            payment_intent_data={
                "setup_future_usage": "off_session"
            }
        )

        return {"checkout_url": checkout_session.url}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ADICIONE ESTA PARTE PARA QUE O RAILWAY DETECTE E USE A PORTA CORRETA
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
