// Vercel serverless function — reports whether a Checkout Session was paid.
// The success page calls this before finalising the order, so a shopper can't
// mint an order just by loading cart.html?paid=1 without actually paying.
const Stripe = require('stripe');

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '');

const ALLOWED_ORIGINS = [
  'https://imjane.top',
  'https://cherishthestudio.com',
  'https://www.cherishthestudio.com',
  'http://localhost:8000',
];

function applyCors(req, res) {
  const origin = req.headers.origin;
  if (ALLOWED_ORIGINS.includes(origin)) res.setHeader('Access-Control-Allow-Origin', origin);
  res.setHeader('Vary', 'Origin');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

module.exports = async (req, res) => {
  applyCors(req, res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (!process.env.STRIPE_SECRET_KEY) {
    return res.status(500).json({ error: 'Stripe not configured' });
  }

  const id = req.query.id;
  if (!id) return res.status(400).json({ error: 'Missing session id' });

  try {
    const s = await stripe.checkout.sessions.retrieve(String(id));
    return res.status(200).json({
      payment_status: s.payment_status, // 'paid' | 'unpaid' | 'no_payment_required'
      amount_total: s.amount_total,
      email: (s.customer_details && s.customer_details.email) || null,
    });
  } catch (err) {
    return res.status(404).json({ error: 'Session not found' });
  }
};
