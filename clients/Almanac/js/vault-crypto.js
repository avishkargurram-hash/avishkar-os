/* Zero-knowledge vault crypto (Web Crypto API). The master password never leaves this device and the server only ever
   sees ciphertext. PBKDF2-SHA256 -> AES-256-GCM. Each record is sealed with its sync key as AAD, so a record cannot be
   swapped under a different key without failing authentication. */
(function(root){
  'use strict';
  const subtle = () => { const c = root.crypto; if(!c || !c.subtle) throw new Error('Secure context required (HTTPS) for the vault'); return c.subtle; };
  const enc = new TextEncoder(), dec = new TextDecoder();
  const ITER = 310000, VERIFY = 'almanac-vault-ok:v1';

  function b64(u8){
    let s = '';
    for(let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function unb64(s){
    const bin = atob(s), u = new Uint8Array(bin.length);
    for(let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    return u;
  }
  function rand(n){ const u = new Uint8Array(n); root.crypto.getRandomValues(u); return u; }

  async function derive(password, salt, iter){
    const base = await subtle().importKey('raw', enc.encode(String(password).normalize('NFKC')), 'PBKDF2', false, ['deriveKey']);
    return subtle().deriveKey({ name:'PBKDF2', salt, iterations: iter, hash:'SHA-256' }, base,
      { name:'AES-GCM', length:256 }, false, ['encrypt', 'decrypt']);
  }

  /* Sealed JSON value: { v:1, iv, ct } (what the server stores for vh:/vd:/vp: records). */
  async function seal(key, obj, aad){
    const iv = rand(12);
    const ct = await subtle().encrypt({ name:'AES-GCM', iv, additionalData: enc.encode(aad) }, key, enc.encode(JSON.stringify(obj)));
    return { v:1, iv: b64(iv), ct: b64(new Uint8Array(ct)) };
  }
  async function open(key, rec, aad){
    if(!rec || rec.v !== 1) throw new Error('Unsupported vault record');
    const pt = await subtle().decrypt({ name:'AES-GCM', iv: unb64(rec.iv), additionalData: enc.encode(aad) }, key, unb64(rec.ct));
    return JSON.parse(dec.decode(pt));
  }

  /* vmeta { salt, ver, iter } lets any device check a password without holding any vault record. */
  async function createMeta(password, iter){
    iter = iter || ITER;
    const salt = rand(16), key = await derive(password, salt, iter);
    const r = await seal(key, { c: VERIFY }, 'vmeta');
    const packed = new Uint8Array(12 + unb64(r.ct).length);
    packed.set(unb64(r.iv), 0); packed.set(unb64(r.ct), 12);
    return { meta: { salt: b64(salt), ver: b64(packed), iter }, key };
  }
  /* Returns the AES key if the password is right, otherwise null. */
  async function unlock(password, meta){
    try{
      const key = await derive(password, unb64(meta.salt), meta.iter);
      const packed = unb64(meta.ver);
      const o = await open(key, { v:1, iv: b64(packed.subarray(0, 12)), ct: b64(packed.subarray(12)) }, 'vmeta');
      return o && o.c === VERIFY ? key : null;
    }catch(e){ return null; }
  }

  /* 20 characters from an unambiguous alphabet; rejection sampling avoids modulo bias. */
  function generatePassword(len, opts){
    opts = opts || {};
    let set = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    if(opts.symbols !== false) set += '!@#$%^&*-_=+?';
    const out = [], max = Math.floor(256 / set.length) * set.length;
    while(out.length < (len || 20)){
      const b = rand(32);
      for(let i = 0; i < b.length && out.length < (len || 20); i++) if(b[i] < max) out.push(set[b[i] % set.length]);
    }
    return out.join('');
  }

  root.VaultCrypto = { ITER, b64, unb64, derive, seal, open, createMeta, unlock, generatePassword };
})(typeof window !== 'undefined' ? window : globalThis);
