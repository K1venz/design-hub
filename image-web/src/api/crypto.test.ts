import { describe, expect, it } from 'vitest'

import { bufferToBase64, pemToDer } from '@/api/crypto'

describe('bufferToBase64', () => {
  it('编码字节为标准 base64', () => {
    expect(bufferToBase64(new Uint8Array([1, 2, 3]).buffer)).toBe('AQID')
    expect(bufferToBase64(new Uint8Array([]).buffer)).toBe('')
    expect(bufferToBase64(new Uint8Array([255, 254, 253]).buffer)).toBe('//79')
  })
})

describe('pemToDer', () => {
  it('去 header/footer/空白并 base64 解码为 DER', () => {
    const pem = '-----BEGIN PUBLIC KEY-----\nAQIDBAU=\n-----END PUBLIC KEY-----\n'
    expect(Array.from(new Uint8Array(pemToDer(pem)))).toEqual([1, 2, 3, 4, 5])
  })

  it('容忍多行 base64 与 CRLF', () => {
    const pem = '-----BEGIN PUBLIC KEY-----\r\nAQID\r\nBAU=\r\n-----END PUBLIC KEY-----'
    expect(Array.from(new Uint8Array(pemToDer(pem)))).toEqual([1, 2, 3, 4, 5])
  })

  it('与 bufferToBase64 往返一致', () => {
    const bytes = new Uint8Array([9, 8, 7, 6, 5, 4, 3, 2, 1, 0])
    const pem = `-----BEGIN PUBLIC KEY-----\n${bufferToBase64(bytes.buffer)}\n-----END PUBLIC KEY-----`
    expect(Array.from(new Uint8Array(pemToDer(pem)))).toEqual(Array.from(bytes))
  })
})
