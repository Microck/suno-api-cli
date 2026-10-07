import { createDecipheriv, createHash } from 'node:crypto';

export interface MangoRights {
  key: string;
  iv: string;
}

/** Unwrap Suno-issued playback keys, then decrypt the progressive audio stream. */
export function createAudioDecipher(clipId: string, rights: MangoRights, sessionToken: string) {
  const wrappingKey = createHash('sha256').update(sessionToken).digest();
  const unwrap = (encoded: string) => {
    const wrapped = Buffer.from(encoded, 'base64');
    const decipher = createDecipheriv('aes-256-gcm', wrappingKey, wrapped.subarray(0, 12));
    decipher.setAAD(Buffer.from(clipId));
    decipher.setAuthTag(wrapped.subarray(-16));
    return Buffer.concat([decipher.update(wrapped.subarray(12, -16)), decipher.final()]);
  };
  return createDecipheriv('aes-128-ctr', unwrap(rights.key), unwrap(rights.iv));
}
