import { NextResponse, NextRequest } from 'next/server';
import { cookies } from 'next/headers';
import { sunoApi } from '@/lib/SunoApi';

export const dynamic = 'force-dynamic';

async function check(request: NextRequest) {
  try {
    const api = await sunoApi((await cookies()).toString());
    if (request.method === 'POST') {
      // A diagnostic solve consumes the token without submitting a song.
      const result = await api.getCaptcha();
      return NextResponse.json({ solved: result.token !== null, provider: result.token_provider });
    }
    return NextResponse.json(await api.captchaStatus());
  } catch {
    return NextResponse.json({ error: 'CAPTCHA check failed. Check authentication and the 2Captcha account.' }, { status: 502 });
  }
}

export const GET = check;
export const POST = check;
