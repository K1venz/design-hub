// 密码传输公钥加密（登录健壮性 §三.0）。WebCrypto RSA-OAEP-SHA256 加密明文密码 → base64 密文，
// 后端私钥解密后照旧 bcrypt。铁律：公钥不可用 = 明确报错、绝不回退明文（静默回退=假加密）。

/** SPKI PEM → DER ArrayBuffer（去 header/footer + 空白，base64 解码）。 */
export function pemToDer(pem: string): ArrayBuffer {
  const b64 = pem
    .replace(/-----BEGIN [^-]+-----/, '')
    .replace(/-----END [^-]+-----/, '')
    .replace(/\s+/g, '')
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes.buffer
}

/** ArrayBuffer → 标准 base64。 */
export function bufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ''
  for (const b of bytes) bin += String.fromCharCode(b)
  return btoa(bin)
}

async function importPublicKey(): Promise<CryptoKey> {
  // 公钥端点公开（无鉴权），走原生 fetch（不经鉴权 client）。容错 JSON{public_key}（coordinator #1019
  // 拍板式）或 text/plain 裸 PEM——看内容像 JSON 就解析，不依赖 Content-Type（防原子上线头抖动）。
  const res = await fetch('/api/auth/pubkey', { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`pubkey ${res.status}`)
  const raw = (await res.text()).trim()
  let pem = raw
  if (raw.startsWith('{')) {
    pem = (JSON.parse(raw) as { public_key?: string }).public_key ?? ''
  }
  if (!pem.includes('BEGIN')) throw new Error('pubkey malformed')
  return crypto.subtle.importKey('spki', pemToDer(pem), { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['encrypt'])
}

// 公钥可缓存（spec：公开、可缓存）：进程内缓存导入结果；失败清缓存以便重试。
let keyPromise: Promise<CryptoKey> | null = null
function getPublicKey(): Promise<CryptoKey> {
  if (!keyPromise) {
    keyPromise = importPublicKey().catch((e) => {
      keyPromise = null
      throw e
    })
  }
  return keyPromise
}

/** 加密明文密码 → base64(RSA-OAEP-SHA256 密文)。公钥不可用则抛（绝不回退明文）。 */
export async function encryptPassword(plain: string): Promise<string> {
  let key: CryptoKey
  try {
    key = await getPublicKey()
  } catch {
    throw new Error('安全通道初始化失败，请刷新页面后重试')
  }
  const cipher = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, key, new TextEncoder().encode(plain))
  return bufferToBase64(cipher)
}
