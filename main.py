from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import stripe

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

app = FastAPI()

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
