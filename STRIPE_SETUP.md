# Stripe checkout — setup

The storefront is static (GitHub Pages). Card payments need a tiny backend to
create Stripe Checkout Sessions (your **secret key must never** live in the
browser). That backend is two Vercel serverless functions in `api/`.

Until you finish these steps, "Place Order" keeps using the **demo flow** (no
real charge) — nothing is broken while you set up.

## 1. Stripe account + test key
1. Create/sign in at https://dashboard.stripe.com
2. Stay in **Test mode** (toggle, top-right) while setting up.
3. Developers → API keys → copy the **Secret key** (`sk_test_...`).

## 2. Deploy the functions to Vercel
1. https://vercel.com → **Add New… → Project** → import `jo1-yo/cherish`.
2. Framework preset: **Other**. Leave build/output empty (it's a static site);
   Vercel auto-detects the `api/` functions and installs `stripe` from
   `package.json`.
3. **Environment Variables** → add:
   - `STRIPE_SECRET_KEY` = `sk_test_...`  (add for Production **and** Preview)
4. Deploy. Note the URL, e.g. `https://cherish-xxxx.vercel.app`.
   - Quick check: `https://cherish-xxxx.vercel.app/api/session-status?id=x`
     should return JSON (a 404 "Session not found" is fine — it means the
     function runs).

## 3. Point the storefront at it
In [`js/app.js`](js/app.js), set:

```js
window.CHECKOUT_API = 'https://cherish-xxxx.vercel.app'; // your Vercel URL
```

Commit + push. That flips checkout from demo → real Stripe.

## 4. Test end-to-end (test mode)
Add something to the bag → **Place Order** → you're sent to Stripe's hosted
checkout. Pay with test card **4242 4242 4242 4242**, any future expiry, any
CVC/ZIP. You return to `cart.html?paid=1`; the app verifies the session was
paid, then records the order and clears the bag.

## 5. Go live
1. Merge `feat/stripe-checkout` → `main`.
2. In Stripe, switch to **live** keys; update `STRIPE_SECRET_KEY` in Vercel to
   `sk_live_...` and redeploy.

## Notes
- Allowed origins are listed in both `api/*.js` (`ALLOWED_ORIGINS`). They cover
  `imjane.top`, `cherishthestudio.com`, and `localhost:8000` — add any others.
- Fulfillment is confirmed on the success redirect via `session-status`. For
  production-grade reliability (shopper closes the tab mid-redirect), add a
  Stripe **webhook** on `checkout.session.completed` later.
- Alternative: host the whole site on Vercel (static + `api/`) and point
  `cherishthestudio.com` there — then checkout is same-origin and you skip CORS.
