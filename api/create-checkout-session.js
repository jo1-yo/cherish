// Vercel serverless function — creates a Stripe Checkout Session from the cart.
// Deploy this repo to Vercel and set the STRIPE_SECRET_KEY env var (use a
// test-mode key, sk_test_..., to start). The static site (on GitHub Pages)
// POSTs here, then redirects the shopper to Stripe's hosted checkout.
const Stripe = require('stripe');

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '');

// Origins allowed to call this endpoint (the storefront). Add your domains.
const ALLOWED_ORIGINS = [
  'https://imjane.top',
  'https://cherishthestudio.com',
  'https://www.cherishthestudio.com',
  'http://localhost:8000',
];

function applyCors(req, res) {
  const origin = req.headers.origin;
  if (ALLOWED_ORIGINS.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
  }
  res.setHeader('Vary', 'Origin');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

// A redirect URL is only accepted if it points back to an allowed origin.
function safeUrl(url) {
  return typeof url === 'string' && ALLOWED_ORIGINS.some((o) => url.startsWith(o));
}

module.exports = async (req, res) => {
  applyCors(req, res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  if (!process.env.STRIPE_SECRET_KEY) {
    return res.status(500).json({ error: 'Stripe not configured (missing STRIPE_SECRET_KEY)' });
  }

  try {
    const { lines = [], shipping = 0, successUrl, cancelUrl } = req.body || {};

    if (!Array.isArray(lines) || lines.length === 0) {
      return res.status(400).json({ error: 'Cart is empty' });
    }
    if (!safeUrl(successUrl) || !safeUrl(cancelUrl)) {
      return res.status(400).json({ error: 'Invalid return URLs' });
    }

    // Each line carries a per-unit price in USD dollars (unit) and a quantity.
    const line_items = lines.map((l) => {
      const unit = Number(l.unit);
      const qty = Math.max(1, Math.floor(Number(l.qty) || 1));
      if (!Number.isFinite(unit) || unit <= 0) throw new Error('Bad line price');
      return {
        quantity: qty,
        price_data: {
          currency: 'usd',
          unit_amount: Math.round(unit * 100), // dollars -> cents
          product_data: {
            name: String(l.name || 'CHERISH piece').slice(0, 240),
            ...(l.detail ? { description: String(l.detail).slice(0, 240) } : {}),
          },
        },
      };
    });

    const ship = Math.max(0, Math.round(Number(shipping) * 100)) || 0;

    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      line_items,
      success_url: successUrl,
      cancel_url: cancelUrl,
      billing_address_collection: 'auto',
      ...(ship > 0
        ? {
            shipping_options: [
              {
                shipping_rate_data: {
                  type: 'fixed_amount',
                  fixed_amount: { amount: ship, currency: 'usd' },
                  display_name: 'Standard shipping',
                },
              },
            ],
          }
        : {}),
    });

    return res.status(200).json({ url: session.url });
  } catch (err) {
    return res.status(500).json({ error: err.message || 'Unable to create checkout session' });
  }
};
