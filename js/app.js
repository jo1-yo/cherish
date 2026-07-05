/* ===========================================================
   CHERISH — shared app logic
   Cart · Favorites · Auth (login gate) · Search · Header/Footer
   State persists in the browser via localStorage.
   =========================================================== */

/* ---------- Product catalogue (The Shimmer Collection) ---------- */
let PRODUCTS = [
  { id:'stardust', name:'Stardust Skirt', cat:'bottoms', price:265, img:'images/look-05.jpg',
    blurb:'Our signature sequinned mini, finished by hand to catch the light with every step. For the extra sparkle in your day.',
    sizes:['XS','S','M','L'] },
  { id:'aurora',   name:'Aurora Skirt',   cat:'bottoms', price:240, img:'images/look-04.jpg',
    blurb:'A blush floral-sequin mini layered over soft undershorts — quietly luminous, made to order.',
    sizes:['XS','S','M','L'] },
  { id:'etoile',   name:'Étoile Bag',     cat:'bags',    price:185, img:'images/still-01.jpg',
    blurb:'A hand-beaded sequin evening bag on a delicate gold chain. Truly one of one.',
    sizes:['One Size'] },
  { id:'lumiere',  name:'Lumière Skirt',  cat:'bottoms', price:255, img:'images/look-03.jpg',
    blurb:'A sheer lace midi with a whisper of sparkle, cut to move with you.',
    sizes:['XS','S','M','L'] },
];
// the admin backend can override the catalogue (stored in the browser)
try{ const _c=JSON.parse(localStorage.getItem('cherish_catalog')); if(Array.isArray(_c)&&_c.length) PRODUCTS=_c; }catch(e){}
const fmt = n => '$' + Number(n).toFixed(0);

/* ---------- Backend API (local dev only — see backend/server.py) ----------
   Real signup (email verification code) and the admin "Registered Users"
   view talk to this. It's only running on localhost:8082 during local
   development; the deployed static site has no backend, so these calls
   simply fail there (callers handle that and explain to the user). */
const API_BASE = 'http://localhost:8082';
const Api = {
  async requestCode(email){
    return Api._post('/api/auth/request-code', {email});
  },
  async verifyCode(email,code,name){
    return Api._post('/api/auth/verify-code', {email,code,name});
  },
  async login(email){
    return Api._post('/api/auth/login', {email});
  },
  async listUsers(){
    const res = await fetch(API_BASE+'/api/admin/users');
    if(!res.ok) throw new Error('backend responded '+res.status);
    return res.json();
  },
  async _post(path,body){
    const res = await fetch(API_BASE+path, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
    });
    const data = await res.json().catch(()=>({}));
    if(!res.ok || !data.ok) throw new Error(data.error || ('backend responded '+res.status));
    return data;
  },
};

/* ---------- Storage ---------- */
const DB = {
  get(k,d){ try{ return JSON.parse(localStorage.getItem('cherish_'+k)) ?? d }catch(e){ return d } },
  set(k,v){ localStorage.setItem('cherish_'+k, JSON.stringify(v)) },
};
const Auth = {
  user(){ return DB.get('user', null) },
  in(){ return !!Auth.user(); },
  login(email,name){ DB.set('user',{email,name:name||email.split('@')[0]}); },
  logout(){ localStorage.removeItem('cherish_user'); },
};
const Cart = {
  all(){ return DB.get('cart', []); },
  count(){ return this.all().reduce((s,i)=>s+i.qty,0); },
  add(id,size,qty=1){
    const c=this.all(); const key=id+'|'+size;
    const hit=c.find(i=>i.key===key);
    if(hit) hit.qty+=qty; else c.push({key,id,size,qty});
    DB.set('cart',c); updateBadges();
  },
  setQty(key,q){ let c=this.all(); const i=c.find(x=>x.key===key); if(i){i.qty=Math.max(1,q);} DB.set('cart',c); updateBadges(); },
  remove(key){ DB.set('cart', this.all().filter(i=>i.key!==key)); updateBadges(); },
  total(){ return this.all().reduce((s,i)=>{ const p=PRODUCTS.find(x=>x.id===i.id); return s+(p?p.price:0)*i.qty; },0); },
  clear(){ DB.set('cart',[]); updateBadges(); },
};
const Fav = {
  all(){ return DB.get('fav', []); },
  has(id){ return this.all().includes(id); },
  toggle(id){
    if(!Auth.in()){
      const here=location.pathname.split('/').pop()+location.search;
      toast('Please sign in to save favorites');
      setTimeout(()=>location.href='login.html?next='+encodeURIComponent(here),750);
      return this.has(id);
    }
    let f=this.all(); f.includes(id)? f=f.filter(x=>x!==id):f.push(id); DB.set('fav',f); updateBadges(); return f.includes(id);
  },
};

/* ---------- Icons ---------- */
const I = {
  search:'<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.5" y2="16.5"/></svg>',
  heart:'<svg viewBox="0 0 24 24"><path d="M12 20.5l-1.4-1.3C5.4 14.5 2 11.4 2 7.6 2 4.9 4.1 3 6.7 3c1.7 0 3.3.8 4.3 2.1C12 3.8 13.6 3 15.3 3 17.9 3 20 4.9 20 7.6c0 3.8-3.4 6.9-8.6 11.6z"/></svg>',
  bag:'<svg viewBox="0 0 24 24"><path d="M3 4h2l2.2 10.2a1 1 0 0 0 1 .8h7.6a1 1 0 0 0 1-.8L19.5 7H6"/><circle cx="9.5" cy="19" r="1.3"/><circle cx="16.5" cy="19" r="1.3"/></svg>',
  user:'<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"/></svg>',
  menu:'<svg viewBox="0 0 24 24"><line x1="3" y1="7" x2="21" y2="7"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="17" x2="21" y2="17"/></svg>',
  instagram:'<svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.2" cy="6.8" r="1.1" fill="currentColor" stroke="none"/></svg>',
};

/* Instagram handle for the brand */
const INSTAGRAM_URL = 'https://www.instagram.com/cherishthestudio?igsh=MWM3MWF0bnNvcnRmeQ==';

/* ---------- Header & Footer injection ---------- */
function renderHeader(active){
  const head = document.getElementById('site-head');
  if(!head) return;
  head.innerHTML = `
  <div class="ticker">Complimentary shipping on first orders · Made to order in New York</div>
  <header class="site-head">
    <div class="nav">
      <button class="menu-toggle" aria-label="Menu" onclick="menuClick()">${I.menu}</button>
      <nav class="nav-center" id="navlinks">
        <button class="nav-close" aria-label="Close menu" onclick="menuClick()">&times;</button>
        <a href="about.html"  class="${active==='about'?'active':''}">About</a>
        <a href="shop.html"   class="${active==='shop'?'active':''}">Shop</a>
        <a href="index.html" class="brand" aria-label="Cherish — home"><img src="images/logo-wordmark.jpg" alt="Cherish"></a>
        <a href="custom.html" class="${active==='custom'?'active':''}">Custom</a>
        <a href="login.html"  class="${active==='login'?'active':''}" id="nav-account">Login</a>
      </nav>
      <div class="nav-icons">
        <button class="icon-btn" aria-label="Search" onclick="toggleSearch()">${I.search}</button>
        <a class="icon-btn heart" href="favorites.html" aria-label="Favorites">${I.heart}<span class="badge" id="b-fav"></span></a>
        <a class="icon-btn cart" href="cart.html" aria-label="Cart" onclick="return cartGate(event)">${I.bag}<span class="badge" id="b-cart"></span></a>
        <a class="icon-btn ig" href="${INSTAGRAM_URL}" target="_blank" rel="noopener" aria-label="Instagram">${I.instagram}</a>
      </div>
    </div>
    <div class="search-bar" id="searchbar">
      <div class="wrap">
        ${I.search}
        <input id="searchinput" type="text" placeholder="Search a piece by name…" autocomplete="off"
               onkeydown="if(event.key==='Enter'){location.href='shop.html?q='+encodeURIComponent(this.value)}">
        <button class="link-underline" onclick="location.href='shop.html?q='+encodeURIComponent(document.getElementById('searchinput').value)">Search</button>
      </div>
    </div>
  </header>`;
  // reflect login state in nav
  const acc = document.getElementById('nav-account');
  if(Auth.in() && acc){ acc.textContent='Account'; acc.href='account.html'; }
  updateBadges();
}

function renderFooter(){
  const f = document.getElementById('site-foot');
  if(!f) return;
  f.innerHTML = `
  <footer class="site-foot">
    <div class="wrap">
      <div class="foot-grid">
        <div>
          <h4>CHERISH</h4>
          <p style="font-size:.9rem;max-width:260px">Ethical, limited-run pieces made to order. For the extra sparkle in your day.</p>
        </div>
        <div>
          <div class="col-title">Explore</div>
          <ul>
            <li><a href="shop.html">Shop</a></li>
            <li><a href="custom.html">Custom Studio</a></li>
            <li><a href="about.html">About</a></li>
            <li><a href="favorites.html">Favorites</a></li>
          </ul>
        </div>
        <div>
          <div class="col-title">Client Care</div>
          <ul>
            <li><a href="info.html#size-chart">Size Chart</a></li>
            <li><a href="info.html#shipping">Shipping</a></li>
            <li><a href="info.html#terms">Terms of Service</a></li>
            <li><a href="info.html#privacy">Privacy Policy</a></li>
            <li><a href="info.html#contact">Contact Us</a></li>
          </ul>
        </div>
        <div>
          <div class="col-title">The List</div>
          <p style="font-size:.86rem;margin-bottom:14px">Early access to limited drops.</p>
          <div class="foot-news">
            <input type="email" placeholder="Email address"
              onkeydown="if(event.key==='Enter'){toast('Welcome to the list');this.value=''}">
          </div>
        </div>
      </div>
      <div class="foot-bottom">
        <span>© ${new Date().getFullYear()} Cherish</span>
        <span>New York, NY</span>
      </div>
    </div>
  </footer>`;
}

/* ---------- UI helpers ---------- */
function updateBadges(){
  const bc=document.getElementById('b-cart'); if(bc){ const n=Cart.count(); bc.textContent=n; bc.dataset.count=n; }
  const bf=document.getElementById('b-fav'); if(bf){ const n=Fav.all().length; bf.textContent=n; bf.dataset.count=n; }
}
/* the hamburger button — pages can override window.menuClick (e.g. Shop opens its category rail) */
function menuClick(){ const n=document.getElementById('navlinks'); if(n) n.classList.toggle('mobile-open'); }
function toggleSearch(){
  const sb=document.getElementById('searchbar'); sb.classList.toggle('open');
  if(sb.classList.contains('open')) setTimeout(()=>document.getElementById('searchinput').focus(),120);
}
function cartGate(e){
  if(!Auth.in()){
    e.preventDefault();
    sessionStorage.setItem('cherish_redirect','cart.html');
    toast('Please sign in to view your bag');
    setTimeout(()=>location.href='login.html?next=cart.html', 700);
    return false;
  }
  return true;
}
let toastTimer;
function toast(msg){
  let t=document.getElementById('toast');
  if(!t){ t=document.createElement('div'); t.id='toast'; t.className='toast'; document.body.appendChild(t); }
  t.textContent=msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.classList.remove('show'),2600);
}

/* tile helper */
function tile(label,cls=''){ return `<div class="tile ${cls}"><span class="tile-label">${label}</span></div>`; }

/* product card */
function productCard(p){
  const on = Fav.has(p.id) ? 'on':'';
  return `<a class="card" href="product.html?id=${p.id}">
    <div class="ph">
      <img src="${p.img}" alt="${p.name}">
      <button class="fav ${on}" aria-label="Favorite" onclick="event.preventDefault();event.stopPropagation();const r=Fav.toggle('${p.id}');this.classList.toggle('on',r);toast(r?'Added to favorites':'Removed');">${I.heart}</button>
    </div>
    <h3>${p.name}</h3>
    <div class="price">${fmt(p.price)}</div>
    <div class="sizes">${p.sizes.join(' · ')}</div>
  </a>`;
}

/* ---------- Homepage content (admin-editable) ---------- */
/* Defaults live in index.html; the admin dashboard can override the four
   category words and any photo slot. Overrides are saved in this browser
   under 'cherish_home' = { cats:[...4], images:{ key:dataURL } }. */
const HOME_DEFAULT_CATS = ['Sustainable','Ethical','Unique','Limited Collection'];
function getHome(){ const h=DB.get('home',{}); return (h&&typeof h==='object')?h:{}; }
function applyHomeContent(){
  const home=getHome();
  const cats=Array.isArray(home.cats)?home.cats:[];
  document.querySelectorAll('[data-cat]').forEach(el=>{
    const i=+el.dataset.cat; if(cats[i]) el.textContent=cats[i];
  });
  const imgs=home.images||{};
  document.querySelectorAll('img[data-img]').forEach(el=>{
    const key=el.dataset.img; if(imgs[key]) el.src=imgs[key];
  });
}

document.addEventListener('DOMContentLoaded',()=>{ updateBadges(); });
