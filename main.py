from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal
from fastapi import APIRouter
import os
import stripe
import time
import hashlib
import requests
import urllib.parse
import hmac, base64
import json
import uuid

def add_sid(url: str) -> str:
    sep = '&' if '?' in url else '?'
    return f"{url}{sep}sid={{CHECKOUT_SESSION_ID}}"

app = FastAPI()

# CORS
origins = origins = [
    "https://learnmoredigitalcourse.com",
    "https://burnjaroformula.online",
    "https://yt2025hub.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https://(.+\.)?(converteai\.net|converteai\.com\.br|vturb\.com)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Env vars
STRIPE_SECRET_KEY   = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET      = os.getenv("STRIPE_WEBHOOK_SECRET")
PIXEL_ID            = os.getenv("PIXEL_ID")
ACCESS_TOKEN        = os.getenv("ACCESS_TOKEN")
UTMIFY_API_URL      = os.getenv("UTMIFY_API_URL")
UTMIFY_API_KEY      = os.getenv("UTMIFY_API_KEY")

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
    customer_email = body.get("customer_email")
    # coletamos os UTMs
    utms = { k: body.get(k, "") for k in (
        "utm_source", 
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content"
    ) }

    if not price_id:
        return JSONResponse(status_code=400, content={"error": "price_id is required"})

    # escolhe a URL de sucesso de acordo com o produto
    if price_id in (
        'price_1Rn3KKEHsMKn9uopolAv2nKU',
        'price_1RwtdeEHsMKn9uop4VqGNZ8F',
        'price_1RxEEGEHsMKn9uopcL2e7CVo',
        'price_1RwT5YEHsMKn9uopjNrvLDMO'
    ):
        success_url = add_sid('https://learnmoredigitalcourse.com/pink-up1-stripe')
    elif price_id in (
        'price_1RpzFgEHsMKn9uop8tE1USBk',
        'price_1RrsCbEHsMKn9uopRnYsH90a'
    ):
        success_url = add_sid('https://learnmoredigitalcourse.com/lipovive-up1-stripe')
    elif price_id == 'price_1Rs89iEHsMKn9uopwkT6I5ya':
        success_url = add_sid('https://learnmoredigitalcourse.com/lipomax-up1-stripe')
    elif price_id == 'price_1RxdG9EHsMKn9uopZQAj9Tjs':
        success_url = add_sid('https://learnmoredigitalcourse.com/teste-pink-up1-stripe')
    else:
        success_url = add_sid('https://burnjaroformula.online/members/')

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{'price': price_id, 'quantity': quantity}],
        mode='payment',
        customer_creation='always',
        customer_email=customer_email,
        phone_number_collection={"enabled": True},
        success_url=success_url,
        cancel_url='https://learnmoredigitalcourse.com/erro',
        # grava UTMs na própria Session
        metadata=utms,
        # grava UTMs também no PaymentIntent
        payment_intent_data={
            "metadata": utms,
            "setup_future_usage": "off_session"
        },
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
    # envia e loga o response para debug
    resp = requests.post(
      f"https://graph.facebook.com/v14.0/{PIXEL_ID}/events",
      params={"access_token": ACCESS_TOKEN},
      json=event_payload
    )
    print("→ InitiateCheckout event sent:", resp.status_code, resp.text)

    # ──────────────────────────────────────────────────
    #  Envia pedido (order) ao UTMify
    cd = session.customer_details or {}
    customer_name  = getattr(cd, "name", "") or ""
    customer_email = getattr(cd, "email", "") or ""
    customer_phone = getattr(cd, "phone", None)
    
    utmify_order = {
      "orderId":       session.id,
      "platform":      "Stripe",
      "paymentMethod": "credit_card",
      "status":        "waiting_payment",
      "createdAt":     time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
      "approvedDate":  None,
      "refundedAt":    None,
      "customer": {
          "name":     customer_name,
          "email":    customer_email,
          "phone":    customer_phone,
          "document": None
      },
      "products": [
        {
          "id":            item.price.id,
          "name":          item.description or item.price.id,
          "planId":        item.price.id,
          "planName":      item.price.nickname or "",
          "quantity":      item.quantity,
          "priceInCents":  item.amount_subtotal
        }
        for item in session.line_items.data
      ],
      "trackingParameters": {
        "utm_source":       session.metadata.get("utm_source",""),
        "utm_medium":       session.metadata.get("utm_medium",""),
        "utm_campaign":     session.metadata.get("utm_campaign",""),
        "utm_term":         session.metadata.get("utm_term",""),
        "utm_content":      session.metadata.get("utm_content","")
      },
      "commission": {
        "totalPriceInCents":     session.amount_total,
        "gatewayFeeInCents":     0,
        "userCommissionInCents": 0,
        "currency":              session.currency.upper()
      }
    }
    resp_utm = requests.post(
      UTMIFY_API_URL,
      headers={
        "Content-Type": "application/json",
        "x-api-token":  UTMIFY_API_KEY
      },
      json=utmify_order
    )
    print("→ Order enviado ao UTMify:", resp_utm.status_code, resp_utm.text)
    # ──────────────────────────────────────────────────

    return {"checkout_url": session.url}

@app.post("/upsell/intent")
async def create_upsell_intent(request: Request):
    stripe.api_key = STRIPE_SECRET_KEY
    body = await request.json()
    sid      = body.get("sid")
    price_id = body.get("price_id")
    quantity = int(body.get("quantity", 1))

    if not sid or not price_id:
        return JSONResponse(status_code=400, content={"error": "sid and price_id are required"})

    # 1) Recupera a Session anterior e extrai customer + payment_method
    sess = stripe.checkout.Session.retrieve(
        sid,
        expand=["payment_intent.payment_method", "customer"]
    )
    if not sess or not sess.customer:
        return JSONResponse(status_code=400, content={"error": "Invalid session or missing customer"})

    customer_id = sess.customer

    # preferimos o PM da PI da Session
    pm = getattr(getattr(sess, "payment_intent", None), "payment_method", None)
    pm_id = pm.id if pm else None

    # fallback: default do customer
    if not pm_id and getattr(sess, "customer", None):
        cust = sess.customer if isinstance(sess.customer, dict) else stripe.Customer.retrieve(customer_id)
        pm_id = (cust.get("invoice_settings", {}) or {}).get("default_payment_method")

    if not pm_id:
        # Sem método salvo? devolve erro orientando a abrir um novo Checkout
        return JSONResponse(status_code=409, content={"error": "No saved payment method; redirect to checkout"})

    # 2) Carrega o price para pegar valor/moeda/identificação
    price = stripe.Price.retrieve(price_id)
    amount_minor = price["unit_amount"] * quantity
    currency = price["currency"]

    # 3) Metadados: copie UTMs da Session anterior e marque como upsell
    base_meta = dict(sess.metadata or {})
    base_meta.update({
        "upsell": "true",
        "parent_session": sid,
        "price_id": price_id,
        "quantity": str(quantity),
    })

    # 4) Idempotência p/ evitar dupla cobrança por duplo clique
    idem_key = f"upsell:{sid}:{price_id}:{quantity}"

    intent = stripe.PaymentIntent.create(
        amount=amount_minor,
        currency=currency,
        customer=customer_id,
        payment_method=pm_id,
        confirmation_method="automatic",   # confirmaremos no front
        metadata=base_meta,
        idempotency_key=idem_key
    )

    return {"client_secret": intent.client_secret, "pm_id": pm_id}

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")

    # 1) Garante que podemos chamar a API do Stripe
    stripe.api_key = STRIPE_SECRET_KEY

    # 2) Valida a assinatura do webhook
    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError as e:
        print("⚠️ Webhook signature mismatch:", e)
        raise HTTPException(400, "Invalid webhook signature")

    # 3) Se for checkout.session.completed, processa
    if event["type"] == "checkout.session.completed":
        session = stripe.checkout.Session.retrieve(
            event["data"]["object"]["id"],
            expand=["line_items"]
        )
        # captura o createdAt original a partir do timestamp da session:
        original_created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(session.created))
        cust = session["customer"]

        # 3.1) Primeiro, guarda as UTMs no Customer
        stripe.Customer.modify(
            cust, 
            metadata=session.metadata,
            name=session.customer_details.name,
            phone=session.customer_details.phone
        )

        # 3.2) Prepara o payload de Purchase para o Meta
        email_hash = hashlib.sha256(
            session.customer_details.email.encode("utf-8")
        ).hexdigest()
        purchase_payload = {
            "data": [{
                "event_name":    "Purchase",
                "event_time":    int(time.time()),
                "event_id":      session.id,
                "action_source": "website",
                "event_source_url": session.url,
                "user_data":     {"em": email_hash},
                "custom_data":   {
                    "currency":     session.currency,
                    "value":        session.amount_total / 100.0,
                    "content_ids":  [li.price.id for li in session.line_items.data],
                    "content_type": "product"
                }
            }]
        }

        # 3.3) Tenta criar a invoice e seus items
        try:
            print(f"🔔 [webhook] criando invoice para sessão {session.id}")

            # 1) InvoiceItem para cada linha
            for item in session.line_items.data:
                ii = stripe.InvoiceItem.create(
                    customer=cust,
                    amount=item.amount_subtotal,
                    currency=session.currency,
                    description=f"{item.description} (Session {session.id})"
                )
                print(
                    f"   → InvoiceItem criado: {ii.id}, "
                    f"valor: {ii.amount/100:.2f} {ii.currency.upper()}"
                )

            # 2) Cria a Invoice em draft (não auto-advance)
            invoice = stripe.Invoice.create(
                customer=cust,
                auto_advance=False,
                collection_method="send_invoice",
                days_until_due=0,
                footer=(
                    "Thank you for purchasing the formula. To access the material, "
                    "simply click on the link and follow the instructions: "
                    "https://burnjaroformula.online/members/\n\n"
                    "If you have any questions, please send an email to: "
                    "digital.solutions.ooh@gmail.com"
                ),
                metadata=dict(session.metadata or {})
            )
            print(
                f"   → Invoice draft criada: {invoice.id}, "
                f"subtotal: {invoice.subtotal/100:.2f} {invoice.currency.upper()}"
            )

            # 3) Finaliza a Invoice para agregar todos os InvoiceItems
            finalized = stripe.Invoice.finalize_invoice(invoice.id)
            print(
                f"   → Invoice finalizada: {finalized.id}, "
                f"valor devida: {finalized.amount_due/100:.2f} "
                f"{finalized.currency.upper()}"
            )

        except Exception as e:
            import traceback
            print("‼️ Erro criando invoice:", e)
            print(traceback.format_exc())

        finally:
            # 4) Mesmo se der erro acima, sempre envia o evento Purchase
            resp = requests.post(
                f"https://graph.facebook.com/v14.0/{PIXEL_ID}/events",
                params={"access_token": ACCESS_TOKEN},
                json=purchase_payload
            )
            print("→ Purchase event sent:", resp.status_code, resp.text)

            # 4.1) Atualiza todo o order como "paid" — POST full payload
            total = session.amount_total
            fee   = total * Decimal("0.0674")   
            net   = total - fee      
            
            utmify_order_paid = {
              "orderId":       session.id,
              "platform":      "Stripe",
              "paymentMethod": "credit_card",
              "status":        "paid",
              "createdAt":     original_created_at,   # timestamp que você calculou lá em cima
              "approvedDate":  time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
              "refundedAt":    None,
              "customer": {
                "name":     session.customer_details.name  or "",
                "email":    session.customer_details.email,
                "phone":    session.customer_details.phone or None,
                "document": None
              },
              "products": [
                {
                  "id":            li.price.id,
                  "name":          li.description or li.price.id,
                  "planId":        li.price.id,
                  "planName":      li.price.nickname or None,
                  "quantity":      li.quantity,
                  "priceInCents":  li.amount_subtotal
                }
                for li in session.line_items.data
              ],
              "trackingParameters": {
                "utm_source":     session.metadata.get("utm_source",""),
                "utm_medium":     session.metadata.get("utm_medium",""),
                "utm_campaign":   session.metadata.get("utm_campaign",""),
                "utm_term":       session.metadata.get("utm_term",""),
                "utm_content":    session.metadata.get("utm_content","")
              },
             "commission": {
                "totalPriceInCents":     float(total),  
                "gatewayFeeInCents":     float(fee),
                "userCommissionInCents": float(net),
                "currency":              session.currency.upper()
             }
            }
            
            resp_utm = requests.post(
              UTMIFY_API_URL,
              headers={
                "Content-Type": "application/json",
                "x-api-token":  UTMIFY_API_KEY
              },
              json=utmify_order_paid
            )
            print("→ Pedido atualizado como pago na UTMify:", resp_utm.status_code, resp_utm.text)

    elif event["type"] == "payment_intent.succeeded":
        # ↳ UPSSELL 1-CLICK (confirmado no front com confirmCardPayment)
        intent_id = event["data"]["object"]["id"]
        intent = stripe.PaymentIntent.retrieve(intent_id, expand=["latest_charge"])

        # Só processa se marcamos como upsell no metadata
        meta = dict(getattr(intent, "metadata", {}) or {})
        if meta.get("upsell") != "true":
            # não é upsell, ignorar
            return JSONResponse({"received": True})

        # ── Dados do cliente (name/email/phone) ──────────────────────────
        email = name = phone = None

        # 1) billing_details da primeira charge
        ch = getattr(intent, "charges", None)
        if ch and getattr(ch, "data", None):
            c0 = ch.data[0]
            bd = getattr(c0, "billing_details", None)
            if bd:
                email = getattr(bd, "email", None) or None
                name  = getattr(bd, "name",  None) or None
                phone = getattr(bd, "phone", None) or None

        if (not email or not name or not phone) and getattr(intent, "latest_charge", None):
            bd = getattr(intent.latest_charge, "billing_details", None)
            if bd:
                email = getattr(bd, "email", None) or email
                name  = getattr(bd, "name",  None) or name
                phone = getattr(bd, "phone", None) or phone

        # 2) fallback: Customer
        cust_id = getattr(intent, "customer", None)
        if cust_id and (not email or not name or not phone):
            cust = stripe.Customer.retrieve(cust_id)
            email = email or (cust.get("email") or None)
            name  = name  or (cust.get("name")  or None)
            phone = phone or (cust.get("phone") or None)

        # ── Cálculos (mesma regra do seu código) ────────────────────────
        total = int(intent.amount)                         # em centavos
        fee   = total * Decimal("0.0674")
        net   = total - fee

        # ── CAPI Purchase (email hash se disponível) ────────────────────
        email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest() if email else None
        purchase_payload = {
            "data": [{
                "event_name": "Purchase",
                "event_time": int(time.time()),
                "event_id":   intent.id,
                "action_source": "website",
                "user_data": ({"em": email_hash} if email_hash else {}),
                "custom_data": {
                    "currency": intent.currency,
                    "value":    total / 100.0,
                    "content_ids":  [meta.get("price_id")] if meta.get("price_id") else [],
                    "content_type": "product"
                }
            }]
        }
        try:
            requests.post(
                f"https://graph.facebook.com/v14.0/{PIXEL_ID}/events",
                params={"access_token": ACCESS_TOKEN},
                json=purchase_payload
            )
        except Exception as e:
            print("→ CAPI (upsell) erro:", e)

        # ── UTMify paid (mantendo campos e comissão como no principal) ──
        utmify_order_paid = {
          "orderId":       intent.id,
          "platform":      "Stripe",
          "paymentMethod": "credit_card",
          "status":        "paid",
          "createdAt":     time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(intent.created)),
          "approvedDate":  time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
          "refundedAt":    None,
          "customer": {
            "name":     name  or "",
            "email":    email or "",
            "phone":    phone or None,
            "document": None
          },
          "products": [
            {
              "id":           meta.get("price_id"),
              "name":         meta.get("price_id") or "Upsell",
              "planId":       meta.get("price_id"),
              "planName":     "Upsell",
              "quantity":     int(meta.get("quantity","1") or "1"),
              "priceInCents": total
            }
          ],
          "trackingParameters": {
            "utm_source":   meta.get("utm_source",""),
            "utm_medium":   meta.get("utm_medium",""),
            "utm_campaign": meta.get("utm_campaign",""),
            "utm_term":     meta.get("utm_term",""),
            "utm_content":  meta.get("utm_content","")
          },
          "commission": {
            "totalPriceInCents":     float(total),
            "gatewayFeeInCents":     float(fee),
            "userCommissionInCents": float(net),
            "currency":              intent.currency.upper()
          }
        }

        try:
            resp_utm = requests.post(
              UTMIFY_API_URL,
              headers={"Content-Type": "application/json","x-api-token": UTMIFY_API_KEY},
              json=utmify_order_paid
            )
            print("→ Upsell pago enviado ao UTMify:", resp_utm.status_code, resp_utm.text)
        except Exception as e:
            print("→ UTMify (upsell) erro:", e)
    
    # 5) Retorna 200 sempre
    return JSONResponse({"received": True})

@app.post("/track-paypal")
async def track_paypal(request: Request):
    raw_body = await request.body()
    # 1) Validação back-and-forth com o PayPal
    verify = requests.post(
        "https://ipnpb.paypal.com/cgi-bin/webscr",
        data=b"cmd=_notify-validate&" + raw_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if verify.text != "VERIFIED":
        return JSONResponse(status_code=400, content={"status": "invalid ipn"})

    # 2) Parse dos dados do IPN
    form = dict(urllib.parse.parse_qsl(raw_body.decode()))
    utm_source       = form.get("custom_utm_source", "")
    utm_medium       = form.get("custom_utm_medium", "")
    utm_campaign     = form.get("custom_utm_campaign", "")
    utm_term         = form.get("custom_utm_term", "")
    utm_content      = form.get("custom_utm_content", "")

    # ───────────────────────────────────────────────────────────
    # 2.5) Dispara o Purchase para a Meta (Facebook) Conversion API
    purchase_payload = {
      "data": [{
        "event_name":    "Purchase",
        "event_time":    int(time.time()),
        "event_id":      form.get("txn_id", ""),              # ID da transação PayPal
        "action_source": "website",
        "event_source_url": form.get("return_url", ""),
        "user_data": {
          "em": hashlib.sha256(
                  form.get("payer_email", "").encode("utf-8")
                ).hexdigest()
        },
        "custom_data": {
          "currency": form.get("mc_currency", ""),
          "value":    float(form.get("mc_gross", 0)),
          "content_ids": [ form.get("item_number", "") ],
          "content_type": "product"
        }
      }]
    }
    requests.post(
      f"https://graph.facebook.com/v14.0/{PIXEL_ID}/events",
      params={"access_token": ACCESS_TOKEN},
      json=purchase_payload
    )

    # 2.5.1) Cria pedido inicial no UTMify (PayPal)
    txn_id = form.get("txn_id", "")
    created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    utmify_order = {
      "orderId":       txn_id,
      "platform":      "PayPal",
      "paymentMethod": "paypal",
      "status":        "waiting_payment",
      "createdAt":     created_at,
      "approvedDate":  None,
      "refundedAt":    None,
      "customer": {
        "email": form.get("payer_email", "")
      },
      "products": [
        {
          "id":           form.get("item_number", ""),
          "name":         form.get("item_name", ""),
          "quantity":     int(form.get("quantity", 1)),
          "priceInCents": int(float(form.get("mc_gross", 0)) * 100)
        }
      ],
      "trackingParameters": {
        "utm_source":      utm_source,
        "utm_medium":      utm_medium,
        "utm_campaign":    utm_campaign,
        "utm_term":        utm_term,
        "utm_content":     utm_content
      },
      "commission": {
        "totalPriceInCents":     int(float(form.get("mc_gross", 0)) * 100),
        "gatewayFeeInCents":     0,
        "userCommissionInCents": 0,
        "currency":              form.get("mc_currency", "").upper()
      }
    }
    resp_utm = requests.post(
      UTMIFY_API_URL,
      headers={
        "Content-Type":  "application/json",
        "x-api-token":   UTMIFY_API_KEY
      },
      json=utmify_order
    )
    print("→ Pedido inicial (PayPal) enviado ao UTMify:", resp_utm.status_code, resp_utm.text)
    # ───────────────────────────────────────────────────────────

    # 3) Cria o cliente na Stripe
    stripe.api_key = STRIPE_SECRET_KEY
    stripe.Customer.create(
        email=form.get("payer_email"),
        metadata={
            "utm_source":   utm_source,
            "utm_medium":   utm_medium,
            "utm_campaign": utm_campaign,
            "utm_term":     utm_term,
            "utm_content":  utm_content,
            "origin":       "paypal"
        }
    )
    return JSONResponse({"status": "ok"})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
