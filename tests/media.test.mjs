import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createAudioDecipher } from '../backend/src/lib/media.ts';

// Fixed wrapped playback keys around the NIST SP 800-38A AES-CTR test vector.
const rights = {
  key: 'AQEBAQEBAQEBAQEBK9t3cysOWOv0kmh5rlTmmn3gor9RidwFXVG/YzWtPxs=',
  iv: 'AgICAgICAgICAgICsPhY74lrsStTxijgNYpvfA1q6SFvMWEAifNGX0/8sHI=',
};

test('playback rights unwrap to the NIST AES-CTR plaintext', () => {
  const decipher = createAudioDecipher('fixture-track', rights, 'fixture-guest-token');
  const plaintext = Buffer.concat([
    decipher.update(Buffer.from('874d6191b620e3261bef6864990db6ce', 'hex')),
    decipher.final(),
  ]);
  assert.equal(plaintext.toString('hex'), '6bc1bee22e409f96e93d7e117393172a');
});

test('rights cannot be reused for another track', () => {
  assert.throws(() => createAudioDecipher('different-track', rights, 'fixture-guest-token'));
});

test('modified wrapped keys and session tokens are rejected', () => {
  const damaged = Buffer.from(rights.key, 'base64');
  damaged[20] ^= 1;
  assert.throws(() => createAudioDecipher('fixture-track', { ...rights, key: damaged.toString('base64') }, 'fixture-guest-token'));
  assert.throws(() => createAudioDecipher('fixture-track', rights, 'different-token'));
});
