import { NextRequest, NextResponse } from 'next/server';
import { Readable } from 'node:stream';
import axios from 'axios';
import { sunoApi } from '@/lib/SunoApi';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const id = new URL(request.url).searchParams.get('id');
  if (!id || !/^[A-Za-z0-9-]+$/.test(id)) {
    return NextResponse.json({ error: 'A valid track id is required.' }, { status: 400 });
  }
  try {
    const audio = await (await sunoApi()).downloadAudio(id);
    const headers = new Headers({ 'Content-Type': audio.contentType, 'Cache-Control': 'no-store' });
    if (audio.length) headers.set('Content-Length', audio.length);
    // SAFETY: Axios and the decipher emit byte buffers; Node's web-stream bridge preserves those chunks.
    const body = Readable.toWeb(audio.stream) as ReadableStream<Uint8Array>;
    return new NextResponse(body, { headers });
  } catch (error) {
    const status = axios.isAxiosError(error) && [403, 404, 429].includes(error.response?.status ?? 0)
      ? error.response!.status : 502;
    return NextResponse.json({ error: 'Suno could not authorize or deliver playable audio.' }, { status });
  }
}
