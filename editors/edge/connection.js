"use strict";
const PilotPatchConnection = {
  isCopilot(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && !url.port && !url.username && !url.password
        && ["copilot.com", "copilot.microsoft.com", "copilot.ai"].includes(url.hostname);
    } catch { return false; }
  },
  validatePair(value, extensionId) {
    if (value?.version !== 1 || value.extension_id !== extensionId
        || !/^[a-f0-9]{64}$/.test(value.token) || !Number.isInteger(value.port)
        || value.port < 1024 || value.port > 65535) throw new Error("Invalid PilotPatch pairing file.");
    return {version: 1, token: value.token, port: value.port, extension_id: extensionId};
  },
  hex(bytes) { return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, "0")).join(""); },
  async key(token) {
    const bytes = Uint8Array.from(token.match(/../g), byte => parseInt(byte, 16));
    return crypto.subtle.importKey("raw", bytes, {name: "HMAC", hash: "SHA-256"}, false, ["sign", "verify"]);
  },
  async sign(key, message) {
    return this.hex(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message)));
  },
  async verify(key, message, proof) {
    if (!/^[a-f0-9]{64}$/.test(proof || "")) return false;
    const bytes = Uint8Array.from(proof.match(/../g), byte => parseInt(byte, 16));
    return crypto.subtle.verify("HMAC", key, bytes, new TextEncoder().encode(message));
  },
  async encryptionKey(key, session) {
    const derived = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`encryption\n${session}`));
    return crypto.subtle.importKey("raw", derived, "AES-GCM", false, ["encrypt", "decrypt"]);
  },
  base64(value) {
    const bytes = new Uint8Array(value);
    let binary = "";
    for (let start = 0; start < bytes.length; start += 32768) {
      binary += String.fromCharCode(...bytes.subarray(start, start + 32768));
    }
    return btoa(binary);
  },
  unbase64(value) { return Uint8Array.from(atob(value), character => character.charCodeAt(0)); },
  async encrypt(key, text, associated) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt({name: "AES-GCM", iv,
      additionalData: new TextEncoder().encode(associated)}, key, new TextEncoder().encode(text));
    return JSON.stringify({iv: this.base64(iv), ciphertext: this.base64(ciphertext)});
  },
  async decrypt(key, text, associated) {
    const envelope = JSON.parse(text), iv = this.unbase64(envelope.iv);
    if (iv.length !== 12) throw new Error("invalid_encryption_nonce");
    const plaintext = await crypto.subtle.decrypt({name: "AES-GCM", iv,
      additionalData: new TextEncoder().encode(associated)}, key, this.unbase64(envelope.ciphertext));
    return new TextDecoder("utf-8", {fatal: true}).decode(plaintext);
  },
  async readBounded(response, maximum = 12000000) {
    if (Number(response.headers.get("content-length")) > maximum) throw new Error("oversized_response");
    const reader = response.body.getReader(), chunks = [];
    let size = 0;
    try {
      for (;;) {
        const {done, value} = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > maximum) throw new Error("oversized_response");
        chunks.push(value);
      }
    } catch (error) { await reader.cancel(); throw error; }
    const output = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { output.set(chunk, offset); offset += chunk.byteLength; }
    return new TextDecoder("utf-8", {fatal: true}).decode(output);
  }
};
if (typeof module !== "undefined") module.exports = PilotPatchConnection;
